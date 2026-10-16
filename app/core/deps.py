from fastapi import Request
from openai import AsyncOpenAI

from app.core.embeddings import Embedder
from app.core.llm import Extractor


def get_extractor(request: Request) -> Extractor:
    return request.app.state.extractor


def get_chat_client(request: Request) -> AsyncOpenAI | None:
    """Tool-calling client for agents; None when unavailable for the configured provider."""
    return getattr(request.app.state, "chat_client", None)


def get_embedder(request: Request) -> Embedder | None:
    """None when semantic matching is off (or no OpenRouter key is configured)."""
    return getattr(request.app.state, "embedder", None)
