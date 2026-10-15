import base64
import logging
import time

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from app import config
from app.core.errors import LLMIncompleteError, LLMRefusalError
from app.core.llm import ExtractionResult, T
from app.core.schemas import UsageInfo

logger = logging.getLogger("recruiting_copilot")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Schema enforcement varies by model/provider on OpenRouter, so we validate locally
# and retry when a model returns JSON that doesn't match the schema.
MAX_ATTEMPTS = 3


class OpenRouterExtractor:
    """Any OpenRouter model via its OpenAI-compatible API, with local schema validation."""

    def __init__(self, client: AsyncOpenAI | None = None):
        if client is None and not config.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to .env (see .env.example).")
        self.client = client or AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            default_headers={"X-Title": "Recruiting Copilot"},
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def extract(
        self,
        *,
        output_type: type[T],
        system_prompt: str,
        instructions: str,
        text: str | None = None,
        pdf: bytes | None = None,
    ) -> ExtractionResult[T]:
        if (text is None) == (pdf is None):
            raise ValueError("Provide exactly one of text or pdf.")

        if pdf is not None:
            user_content = [
                {"type": "text", "text": instructions},
                {
                    "type": "file",
                    "file": {
                        "filename": "resume.pdf",
                        "file_data": "data:application/pdf;base64,"
                        + base64.standard_b64encode(pdf).decode(),
                    },
                },
            ]
        else:
            user_content = f"{instructions}\n\n<document>\n{text}\n</document>"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        start = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                completion = await self.client.chat.completions.parse(
                    model=config.OPENROUTER_MODEL,
                    messages=messages,
                    response_format=output_type,
                    max_tokens=16000,
                    # Only route to providers that actually support json_schema output.
                    extra_body={"provider": {"require_parameters": True}},
                )
            except openai.LengthFinishReasonError:
                raise LLMIncompleteError("Output was cut off (finish_reason=length).")
            except openai.ContentFilterFinishReasonError:
                raise LLMRefusalError("The provider's content filter blocked this document.")
            except ValidationError as e:  # JSON didn't match the schema
                last_error = e
                logger.warning("Schema-invalid output (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, e)
                continue

            # Errors after generation starts arrive as HTTP 200 with no usable choice.
            if not completion.choices:
                raise LLMIncompleteError("Provider returned no output.")
            message = completion.choices[0].message
            if message.refusal:
                raise LLMRefusalError("The model declined to process this document.")
            if message.parsed is None:
                last_error = LLMIncompleteError("Empty response content.")
                logger.warning("Empty output (attempt %d/%d)", attempt, MAX_ATTEMPTS)
                continue
            break
        else:
            raise LLMIncompleteError(f"No schema-valid output after {MAX_ATTEMPTS} attempts: {last_error}")

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = completion.usage
        return ExtractionResult(
            data=message.parsed,
            usage=UsageInfo(
                model=completion.model,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            ),
        )
