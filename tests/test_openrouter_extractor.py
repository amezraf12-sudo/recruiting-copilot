"""OpenRouter extractor tests with a fake OpenAI client: no network, no key."""

import asyncio
from types import SimpleNamespace

import openai
import pytest
from pydantic import BaseModel, ValidationError

from app.core.errors import LLMIncompleteError, LLMRefusalError
from app.core.providers.openrouter_extractor import MAX_ATTEMPTS, OpenRouterExtractor


class Out(BaseModel):
    name: str


def completion(parsed=None, refusal=None, choices=True):
    message = SimpleNamespace(parsed=parsed, refusal=refusal)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)] if choices else [],
        model="test/model",
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def schema_error() -> ValidationError:
    try:
        Out.model_validate_json('{"wrong": 1}')
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


class FakeClient:
    """Returns (or raises) the queued outcomes in order, recording each call."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def close(self):
        pass


def run(client, **kwargs):
    extractor = OpenRouterExtractor(client=client)
    args = {"output_type": Out, "system_prompt": "sys", "instructions": "do it", "text": "doc"}
    return asyncio.run(extractor.extract(**(args | kwargs)))


def test_success_returns_parsed_and_usage():
    client = FakeClient(completion(parsed=Out(name="Maria")))
    result = run(client)
    assert result.data.name == "Maria"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 7)
    call = client.calls[0]
    assert call["response_format"] is Out
    assert call["extra_body"] == {"provider": {"require_parameters": True}}
    assert call["messages"][0] == {"role": "system", "content": "sys"}


def test_retries_after_schema_invalid_output():
    client = FakeClient(schema_error(), completion(parsed=Out(name="Maria")))
    assert run(client).data.name == "Maria"
    assert len(client.calls) == 2


def test_gives_up_after_max_attempts():
    client = FakeClient(*[schema_error()] * MAX_ATTEMPTS)
    with pytest.raises(LLMIncompleteError):
        run(client)
    assert len(client.calls) == MAX_ATTEMPTS


def test_refusal_raises():
    with pytest.raises(LLMRefusalError):
        run(FakeClient(completion(refusal="no")))


def test_no_choices_raises_incomplete():
    with pytest.raises(LLMIncompleteError):
        run(FakeClient(completion(choices=False)))


def test_length_cutoff_raises_incomplete():
    error = openai.LengthFinishReasonError.__new__(openai.LengthFinishReasonError)
    with pytest.raises(LLMIncompleteError):
        run(FakeClient(error))


def test_pdf_is_sent_as_file_part():
    client = FakeClient(completion(parsed=Out(name="Maria")))
    run(client, text=None, pdf=b"%PDF-1.7")
    parts = client.calls[0]["messages"][1]["content"]
    file_part = next(p for p in parts if p["type"] == "file")
    assert file_part["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_requires_exactly_one_input():
    with pytest.raises(ValueError):
        run(FakeClient(), text=None)
