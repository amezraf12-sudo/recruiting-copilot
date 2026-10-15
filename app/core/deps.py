from fastapi import Request

from app.core.llm import Extractor


def get_extractor(request: Request) -> Extractor:
    return request.app.state.extractor
