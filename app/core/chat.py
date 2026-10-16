"""Chat client for tool-calling agents (OpenRouter's OpenAI-compatible API)."""

from openai import AsyncOpenAI

from app import config
from app.core.providers.openrouter_extractor import OPENROUTER_BASE_URL


def create_chat_client() -> AsyncOpenAI | None:
    """None when the provider has no tool-calling client configured (agent routes return 501)."""
    if config.LLM_PROVIDER != "openrouter" or not config.OPENROUTER_API_KEY:
        return None
    return AsyncOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
        default_headers={"X-Title": "Recruiting Copilot"},
    )
