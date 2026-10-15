"""LLM error types and their HTTP mapping, shared by every domain router."""

import logging

import anthropic
import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("recruiting_copilot")


class LLMRefusalError(Exception):
    """The model declined the request (stop_reason == "refusal")."""


class LLMIncompleteError(Exception):
    """The response was cut off or didn't produce a valid structured output."""


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def register_error_handlers(app: FastAPI) -> None:
    # Starlette picks the handler for the most specific class in the exception's MRO,
    # so RateLimitError gets its own 429 even though it subclasses APIStatusError.
    @app.exception_handler(LLMRefusalError)
    async def _refusal(_: Request, exc: LLMRefusalError):
        return _error(422, str(exc))

    @app.exception_handler(LLMIncompleteError)
    async def _incomplete(_: Request, exc: LLMIncompleteError):
        return _error(502, str(exc))

    # Both SDKs (Anthropic direct, OpenAI-compatible for OpenRouter) share the same
    # error class names, so register the same handlers for each.
    for sdk in (anthropic, openai):

        @app.exception_handler(sdk.RateLimitError)
        async def _rate_limit(_: Request, exc: Exception):
            return _error(429, "Upstream rate limit; retry shortly.")

        @app.exception_handler(sdk.AuthenticationError)
        async def _auth(_: Request, exc: Exception):
            logger.error("LLM provider authentication failed; check the API key in .env.")
            return _error(500, "Server misconfigured.")

        @app.exception_handler(sdk.APIStatusError)
        async def _status(_: Request, exc: anthropic.APIStatusError | openai.APIStatusError):
            if exc.status_code == 402:  # OpenRouter: out of credits
                logger.error("LLM provider reports insufficient credits.")
                return _error(503, "LLM provider out of credits.")
            logger.error("LLM API error %s: %s", exc.status_code, exc.message)
            return _error(502, "Upstream LLM error.")

        @app.exception_handler(sdk.APIConnectionError)
        async def _connection(_: Request, exc: Exception):
            return _error(503, "Could not reach LLM provider.")
