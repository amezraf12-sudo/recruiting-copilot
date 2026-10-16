from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from app import config
from app.core.deps import get_embedder, get_extractor
from app.core.embeddings import Embedder
from app.core.llm import Extractor
from app.core.rate_limit import RateLimiter, client_ip, get_limiter, rate_limit
from app.domains.recruiting.schemas import (
    JobTextRequest,
    ParsedJob,
    ParsedResume,
    ResumeTextRequest,
    ScreenRequest,
    ScreenResult,
)
from app.domains.recruiting.service import parse_job, parse_resume, screen

# Every route here calls the LLM, so every route is rate limited (1 call each by default).
router = APIRouter(prefix="/recruiting", tags=["recruiting"], dependencies=[Depends(rate_limit)])


@router.post("/parse-resume", response_model=ParsedResume)
async def parse_resume_text(
    body: ResumeTextRequest, extractor: Extractor = Depends(get_extractor)
) -> ParsedResume:
    return await parse_resume(extractor, text=body.text, as_of=date.today())


@router.post("/parse-resume/file", response_model=ParsedResume)
async def parse_resume_file(
    file: UploadFile, extractor: Extractor = Depends(get_extractor)
) -> ParsedResume:
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")

    if data.startswith(b"%PDF"):
        return await parse_resume(extractor, pdf=data, as_of=date.today())
    if file.content_type == "text/plain":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail="Text file must be UTF-8.")
        return await parse_resume(extractor, text=text, as_of=date.today())
    raise HTTPException(status_code=415, detail="Upload a PDF or a UTF-8 .txt file.")


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
    """Rank up to 10 resumes against one job posting, with reasons for every score."""
    # The router already charged 1 call (the job). Charge the worst case up front: one
    # parse per resume, plus one semantic verification per resume when enabled.
    per_resume = 2 if embedder is not None else 1
    limiter.check(client_ip(request), cost=per_resume * len(body.candidates))
    return await screen(
        extractor, job_description=body.job_description, candidates=body.candidates,
        as_of=date.today(), embedder=embedder,
    )
