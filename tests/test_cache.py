import asyncio

import pytest
from pydantic import BaseModel

from app import config
from app.core.errors import LLMIncompleteError
from app.core.llm import CachingExtractor, ExtractionResult
from app.core.schemas import UsageInfo


class Out(BaseModel):
    value: str
    items: list[str] = []


class CountingExtractor:
    """Returns a new answer per call (like a nondeterministic LLM); can fail on demand."""

    def __init__(self, fail_first: bool = False):
        self.calls = 0
        self.fail_first = fail_first

    async def extract(self, *, output_type, system_prompt, instructions, text=None, pdf=None):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise LLMIncompleteError("bad output")
        return ExtractionResult(
            data=output_type(value=f"answer-{self.calls}"),
            usage=UsageInfo(model="m", input_tokens=100, output_tokens=50, latency_ms=900),
        )

    async def aclose(self):
        pass


def extract(cache, text="resume", pdf=None, prompt="sys"):
    return asyncio.run(cache.extract(output_type=Out, system_prompt=prompt, instructions="go",
                                     text=None if pdf else text, pdf=pdf))


def test_same_input_returns_same_answer_without_a_second_call():
    inner = CountingExtractor()
    cache = CachingExtractor(inner, max_entries=10)
    first, second = extract(cache), extract(cache)
    assert first.data == second.data and inner.calls == 1
    assert (second.usage.input_tokens, second.usage.output_tokens, second.usage.latency_ms) == (0, 0, 0)
    assert first.usage.input_tokens == 100  # the real call reports real usage


def test_different_inputs_are_cached_separately():
    inner = CountingExtractor()
    cache = CachingExtractor(inner, max_entries=10)
    extract(cache, text="a"), extract(cache, text="b"), extract(cache, text="a", prompt="other")
    extract(cache, pdf=b"%PDF a")
    assert inner.calls == 4


def test_model_change_is_a_cache_miss(monkeypatch):
    inner = CountingExtractor()
    cache = CachingExtractor(inner, max_entries=10)
    extract(cache)
    monkeypatch.setattr(config, "OPENROUTER_MODEL", "some/other-model")
    extract(cache)
    assert inner.calls == 2


def test_failures_are_not_cached():
    inner = CountingExtractor(fail_first=True)
    cache = CachingExtractor(inner, max_entries=10)
    with pytest.raises(LLMIncompleteError):
        extract(cache)
    assert extract(cache).data.value == "answer-2"


def test_least_recently_used_entry_is_evicted():
    inner = CountingExtractor()
    cache = CachingExtractor(inner, max_entries=2)
    extract(cache, "a"), extract(cache, "b"), extract(cache, "a"), extract(cache, "c")  # evicts b
    calls = inner.calls
    extract(cache, "a")
    assert inner.calls == calls  # still cached
    extract(cache, "b")
    assert inner.calls == calls + 1  # was evicted


def test_callers_cannot_mutate_the_cached_result():
    cache = CachingExtractor(CountingExtractor(), max_entries=10)
    extract(cache).data.items.append("tampered")
    assert extract(cache).data.items == []
