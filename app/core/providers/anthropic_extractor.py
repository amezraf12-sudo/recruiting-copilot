import base64
import time

from anthropic import AsyncAnthropic

from app import config
from app.core.errors import LLMIncompleteError, LLMRefusalError
from app.core.llm import ExtractionResult, T
from app.core.schemas import UsageInfo


class AnthropicExtractor:
    """Claude via the Anthropic API: schema enforced server-side by structured outputs."""

    def __init__(self, client: AsyncAnthropic | None = None):
        self.client = client or AsyncAnthropic()

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
            content = [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf).decode(),
                    },
                },
                {"type": "text", "text": instructions},
            ]
        else:
            content = f"{instructions}\n\n<document>\n{text}\n</document>"

        start = time.perf_counter()
        response = await self.client.beta.messages.parse(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            output_format=output_type,
            output_config={"effort": config.CLAUDE_EFFORT},
            # If a safety classifier declines, the API retries on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.stop_reason == "refusal":
            raise LLMRefusalError("The model declined to process this document.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise LLMIncompleteError(f"No valid output (stop_reason={response.stop_reason}).")

        return ExtractionResult(
            data=response.parsed_output,
            usage=UsageInfo(
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
            ),
        )
