"""Domain-agnostic structured extraction: unstructured text/PDF -> validated Pydantic model.

Every domain (recruiting, support tickets, invoices, ...) reuses this; a domain only
supplies its output schema and prompts. The LLM provider is chosen by LLM_PROVIDER.
"""

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from app import config
from app.core.schemas import UsageInfo

T = TypeVar("T", bound=BaseModel)


@dataclass
class ExtractionResult(Generic[T]):
    data: T
    usage: UsageInfo


class Extractor(Protocol):
    async def extract(
        self,
        *,
        output_type: type[T],
        system_prompt: str,
        instructions: str,
        text: str | None = None,
        pdf: bytes | None = None,
    ) -> ExtractionResult[T]: ...

    async def aclose(self) -> None: ...


def create_extractor() -> Extractor:
    if config.LLM_PROVIDER == "openrouter":
        from app.core.providers.openrouter_extractor import OpenRouterExtractor

        return OpenRouterExtractor()
    if config.LLM_PROVIDER == "anthropic":
        from app.core.providers.anthropic_extractor import AnthropicExtractor

        return AnthropicExtractor()
    raise ValueError(f"Unknown LLM_PROVIDER={config.LLM_PROVIDER!r}; use 'openrouter' or 'anthropic'.")
