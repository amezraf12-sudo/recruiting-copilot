from fastapi import Request

from app.core.embeddings import Embedder
from app.core.llm import Extractor


def get_extractor(request: Request) -> Extractor:
    return request.app.state.extractor


def get_embedder(request: Request) -> Embedder | None:
    """None when semantic matching is off (or no OpenRouter key is configured)."""
    return getattr(request.app.state, "embedder", None)
