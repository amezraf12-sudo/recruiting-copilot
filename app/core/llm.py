"""Domain-agnostic structured extraction: unstructured text/PDF -> validated Pydantic model.

Every domain (recruiting, support tickets, invoices, ...) reuses this; a domain only
supplies its output schema and prompts. The LLM provider is chosen by LLM_PROVIDER.
"""

import hashlib
from collections import OrderedDict
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


def _active_model() -> str:
    return config.OPENROUTER_MODEL if config.LLM_PROVIDER == "openrouter" else config.CLAUDE_MODEL


class CachingExtractor:
    """Same input -> same output: an in-memory LRU cache in front of any Extractor.

    LLM extraction varies slightly between calls (seen in evals: a job parsed with 3 bonus
    skills one time and 4 the next, changing a score by 1 point). Caching by exact input makes
    repeated requests consistent, faster and free. The key covers model, schema, prompts and
    document. Failures are not cached. The cache is per process, so it resets on restart.
    """

    def __init__(self, inner: Extractor, max_entries: int):
        self.inner = inner
        self.max_entries = max_entries
        self._cache: OrderedDict[str, ExtractionResult] = OrderedDict()
        self.hits = 0

    @staticmethod
    def _key(output_type, system_prompt, instructions, text, pdf) -> str:
        h = hashlib.sha256()
        for part in (config.LLM_PROVIDER, _active_model(), output_type.__qualname__,
                     system_prompt, instructions):
            h.update(part.encode() + b"\x00")
        h.update(b"text\x00" + text.encode() if text is not None else b"pdf\x00" + (pdf or b""))
        return h.hexdigest()

    async def extract(self, *, output_type, system_prompt, instructions, text=None, pdf=None):
        key = self._key(output_type, system_prompt, instructions, text, pdf)
        if key in self._cache:
            self._cache.move_to_end(key)
            self.hits += 1
            cached = self._cache[key]
            # A copy, so callers can't mutate the cached result; zero usage: no call was made.
            return ExtractionResult(
                data=cached.data.model_copy(deep=True),
                usage=cached.usage.model_copy(update={"input_tokens": 0, "output_tokens": 0,
                                                      "latency_ms": 0}),
            )
        result = await self.inner.extract(
            output_type=output_type, system_prompt=system_prompt, instructions=instructions,
            text=text, pdf=pdf,
        )
        self._cache[key] = result
        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return ExtractionResult(data=result.data.model_copy(deep=True), usage=result.usage)

    async def aclose(self) -> None:
        await self.inner.aclose()


def create_extractor(cache: bool = True) -> Extractor:
    """cache=False for evals, which must measure fresh model behavior on every call."""
    if config.LLM_PROVIDER == "openrouter":
        from app.core.providers.openrouter_extractor import OpenRouterExtractor

        extractor: Extractor = OpenRouterExtractor()
    elif config.LLM_PROVIDER == "anthropic":
        from app.core.providers.anthropic_extractor import AnthropicExtractor

        extractor = AnthropicExtractor()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER={config.LLM_PROVIDER!r}; use 'openrouter' or 'anthropic'.")
    if cache and config.LLM_CACHE_MAX_ENTRIES > 0:
        return CachingExtractor(extractor, config.LLM_CACHE_MAX_ENTRIES)
    return extractor
