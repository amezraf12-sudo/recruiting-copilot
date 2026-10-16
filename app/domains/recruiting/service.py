import asyncio
import time
from dataclasses import dataclass
from datetime import date

from app.core.embeddings import Embedder
from app.core.errors import LLMIncompleteError, LLMRefusalError
from app.core.llm import Extractor
from app.domains.recruiting.experience import total_years_experience
from app.domains.recruiting.matching import rank, score_candidate
from app.domains.recruiting.prompts import (
    JOB_INSTRUCTIONS,
    JOB_SYSTEM_PROMPT,
    RESUME_INSTRUCTIONS,
    RESUME_SYSTEM_PROMPT,
)
from app.domains.recruiting.schemas import (
    CandidateError,
    CandidateInput,
    JobRequirements,
    ParsedJob,
    ParsedResume,
    ResumeExtraction,
    ScreenResult,
    ScreenUsage,
)
from app.domains.recruiting.semantic import find_semantic_matches
from app.domains.recruiting.seniority import infer_seniority

MAX_CONCURRENT_LLM_CALLS = 4


async def parse_resume(
    extractor: Extractor,
    *,
    as_of: date,
    text: str | None = None,
    pdf: bytes | None = None,
) -> ParsedResume:
    result = await extractor.extract(
        output_type=ResumeExtraction,
        system_prompt=RESUME_SYSTEM_PROMPT,
        instructions=RESUME_INSTRUCTIONS,
        text=text,
        pdf=pdf,
    )
    years = total_years_experience(result.data.experience, as_of)
    return ParsedResume(
        profile=result.data,
        total_years_experience=years,
        seniority=infer_seniority(result.data.seniority_signals, years),
        usage=result.usage,
    )


async def parse_job(extractor: Extractor, *, text: str) -> ParsedJob:
    result = await extractor.extract(
        output_type=JobRequirements,
        system_prompt=JOB_SYSTEM_PROMPT,
        instructions=JOB_INSTRUCTIONS,
        text=text,
    )
    return ParsedJob(requirements=result.data, usage=result.usage)


@dataclass
class ResumeDoc:
    """One resume to screen: plain text or PDF bytes (exactly one)."""

    id: str
    text: str | None = None
    pdf: bytes | None = None

    @classmethod
    def from_input(cls, candidate: CandidateInput) -> "ResumeDoc":
        return cls(id=candidate.id, text=candidate.text)


async def screen(
    extractor: Extractor,
    *,
    job_description: str,
    candidates: list[ResumeDoc],
    as_of: date,
    embedder: Embedder | None = None,
) -> ScreenResult:
    """Parse the job and every resume concurrently, then score and rank in code.

    With an embedder, skills that exact matching missed get a semantic pass (retrieve with
    embeddings, check with one LLM call per candidate). Its results are attached as
    suggestions for the recruiter and never change scores or ranking.
    """
    ids = [c.id for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("Candidate ids must be unique.")  # results are keyed by id
    start = time.perf_counter()
    sem = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

    async def limited(coro):
        async with sem:
            return await coro

    job_task = limited(parse_job(extractor, text=job_description))
    resume_tasks = [
        limited(parse_resume(extractor, text=c.text, pdf=c.pdf, as_of=as_of)) for c in candidates
    ]
    # The job must parse; a single bad resume shouldn't sink the whole screen.
    job, *resumes = await asyncio.gather(job_task, *resume_tasks, return_exceptions=True)
    if isinstance(job, BaseException):
        raise job

    parsed: dict[str, ParsedResume] = {}
    errors = []
    usages = [job.usage]
    for candidate, resume in zip(candidates, resumes):
        if isinstance(resume, (LLMRefusalError, LLMIncompleteError)):
            errors.append(CandidateError(candidate_id=candidate.id, error=str(resume)))
            continue
        if isinstance(resume, BaseException):
            raise resume  # provider-level failure (auth, rate limit, outage): fail the request
        usages.append(resume.usage)
        parsed[candidate.id] = resume

    suggestions: dict[str, dict[str, str]] = {}
    embedding_tokens = 0
    if embedder is not None and parsed:
        semantic = await find_semantic_matches(
            embedder, extractor, job.requirements, parsed, MAX_CONCURRENT_LLM_CALLS
        )
        suggestions = semantic.matches
        usages += semantic.llm_usages
        embedding_tokens = semantic.embedding_tokens

    matches = [
        score_candidate(cid, resume, job.requirements, suggestions.get(cid))
        for cid, resume in parsed.items()
    ]
    return ScreenResult(
        job=job.requirements,
        ranking=rank(matches),
        errors=errors,
        usage=ScreenUsage(
            llm_calls=len(usages),
            input_tokens=sum(u.input_tokens for u in usages),
            output_tokens=sum(u.output_tokens for u in usages),
            embedding_tokens=embedding_tokens,
            latency_ms=int((time.perf_counter() - start) * 1000),
        ),
    )
