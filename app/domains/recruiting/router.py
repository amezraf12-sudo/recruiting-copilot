from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from openai import AsyncOpenAI

from app import config
from app.core.deps import get_chat_client, get_embedder, get_extractor
from app.core.embeddings import Embedder
from app.core.llm import Extractor
from app.core.rate_limit import RateLimiter, client_ip, get_limiter, rate_limit
from app.domains.recruiting.assistant import run_assistant
from app.domains.recruiting.schemas import (
    AssistantRequest,
    AssistantResponse,
    JobTextRequest,
    ParsedJob,
    ParsedResume,
    ResumeTextRequest,
    ScreenRequest,
    ScreenResult,
)
from app.domains.recruiting.service import ResumeDoc, parse_job, parse_resume, screen

MAX_SCREEN_FILES = 10

# Every route here calls the LLM, so every route is rate limited (1 call each by default).
router = APIRouter(prefix="/recruiting", tags=["recruiting"], dependencies=[Depends(rate_limit)])


async def read_resume_upload(file: UploadFile) -> tuple[str | None, bytes | None]:
    """Validate an uploaded resume; returns (text, None) or (None, pdf_bytes)."""
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{file.filename}: file too large.")
    if data.startswith(b"%PDF"):
        return None, data
    if file.content_type == "text/plain":
        try:
            return data.decode("utf-8"), None
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail=f"{file.filename}: text must be UTF-8.")
    raise HTTPException(status_code=415, detail=f"{file.filename}: upload a PDF or a UTF-8 .txt file.")


def charge_screen(request: Request, limiter: RateLimiter, embedder: Embedder | None, n: int) -> None:
    # The router already charged 1 call (the job). Charge the worst case up front: one
    # parse per resume, plus one semantic check per resume when enabled.
    per_resume = 2 if embedder is not None else 1
    limiter.check(client_ip(request), cost=per_resume * n)


@router.post("/parse-resume", response_model=ParsedResume)
async def parse_resume_text(
    body: ResumeTextRequest, extractor: Extractor = Depends(get_extractor)
) -> ParsedResume:
    return await parse_resume(extractor, text=body.text, as_of=date.today())


@router.post("/parse-resume/file", response_model=ParsedResume)
async def parse_resume_file(
    file: UploadFile, extractor: Extractor = Depends(get_extractor)
) -> ParsedResume:
    text, pdf = await read_resume_upload(file)
    return await parse_resume(extractor, text=text, pdf=pdf, as_of=date.today())


@router.post("/parse-job", response_model=ParsedJob)
async def parse_job_text(
    body: JobTextRequest, extractor: Extractor = Depends(get_extractor)
) -> ParsedJob:
    return await parse_job(extractor, text=body.text)


@router.post("/screen", response_model=ScreenResult)
async def screen_candidates(
    body: ScreenRequest,
    request: Request,
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder | None = Depends(get_embedder),
    limiter: RateLimiter = Depends(get_limiter),
) -> ScreenResult:
    """Rank up to 10 plain-text resumes against one job posting, with reasons for every score."""
    charge_screen(request, limiter, embedder, len(body.candidates))
    return await screen(
        extractor, job_description=body.job_description,
        candidates=[ResumeDoc.from_input(c) for c in body.candidates],
        as_of=date.today(), embedder=embedder,
    )


@router.post("/assistant", response_model=AssistantResponse)
async def assistant(
    body: AssistantRequest,
    request: Request,
    client: AsyncOpenAI | None = Depends(get_chat_client),
    limiter: RateLimiter = Depends(get_limiter),
) -> AssistantResponse:
    """Ask the recruiter assistant about a completed screen. It proposes outreach emails and
    screening questions for review; it never sends anything."""
    if client is None:
        raise HTTPException(status_code=501, detail="The assistant requires LLM_PROVIDER=openrouter.")
    ip = client_ip(request)
    # The router charged the first model call; charge each further agent step as it happens.
    return await run_assistant(client, body, on_step=lambda _: limiter.check(ip))


@router.post("/screen/upload", response_model=ScreenResult)
async def screen_uploaded(
    request: Request,
    job_description: str = Form(min_length=50, max_length=20_000),
    files: list[UploadFile] = File(description="1-10 resumes, PDF or UTF-8 .txt"),
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder | None = Depends(get_embedder),
    limiter: RateLimiter = Depends(get_limiter),
) -> ScreenResult:
    """Rank up to 10 uploaded resumes (PDF or .txt) against one job posting."""
    if not 1 <= len(files) <= MAX_SCREEN_FILES:
        raise HTTPException(status_code=422, detail=f"Upload 1-{MAX_SCREEN_FILES} resumes.")
    charge_screen(request, limiter, embedder, len(files))

    docs, seen = [], set()
    for i, file in enumerate(files, start=1):
        text, pdf = await read_resume_upload(file)
        # Candidate ids come from file names; duplicates get a numeric suffix.
        base = file.filename or f"resume-{i}"
        cid, n = base, 2
        while cid in seen:
            cid, n = f"{base} ({n})", n + 1
        seen.add(cid)
        docs.append(ResumeDoc(id=cid, text=text, pdf=pdf))

    return await screen(
        extractor, job_description=job_description, candidates=docs,
        as_of=date.today(), embedder=embedder,
    )
