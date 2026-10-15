from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app import config
from app.core.deps import get_extractor
from app.core.llm import Extractor
from app.domains.recruiting.schemas import ParsedResume, ResumeTextRequest
from app.domains.recruiting.service import parse_resume

router = APIRouter(prefix="/recruiting", tags=["recruiting"])


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
