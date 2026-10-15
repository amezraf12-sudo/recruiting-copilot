from datetime import date

from app.core.llm import Extractor
from app.domains.recruiting.experience import total_years_experience
from app.domains.recruiting.prompts import RESUME_INSTRUCTIONS, RESUME_SYSTEM_PROMPT
from app.domains.recruiting.schemas import ParsedResume, ResumeExtraction
from app.domains.recruiting.seniority import infer_seniority


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
