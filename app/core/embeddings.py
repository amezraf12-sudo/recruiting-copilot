"""Text embeddings for semantic matching, with an in-process cache.

Skill phrases repeat constantly across resumes and jobs ("PostgreSQL", "React"), so caching
by exact text avoids paying for the same embedding twice.
"""

import math

from openai import AsyncOpenAI

from app import config
from app.core.providers.openrouter_extractor import OPENROUTER_BASE_URL

MAX_BATCH = 256


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


class Embedder:
    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None):
        if client is None and not config.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to .env (see .env.example).")
        self.client = client or AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            default_headers={"X-Title": "Recruiting Copilot"},
        )
        self.model = model or config.OPENROUTER_EMBEDDING_MODEL
        self._cache: dict[str, list[float]] = {}
        self.tokens_used = 0

    async def aclose(self) -> None:
        await self.client.close()

    async def embed(self, texts: list[str]) -> dict[str, list[float]]:
        """Embeddings for every text, calling the API only for texts not cached yet."""
        missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
        for i in range(0, len(missing), MAX_BATCH):
            batch = missing[i : i + MAX_BATCH]
            response = await self.client.embeddings.create(model=self.model, input=batch)
            for text, item in zip(batch, sorted(response.data, key=lambda d: d.index)):
                self._cache[text] = item.embedding
            if response.usage:
                self.tokens_used += response.usage.prompt_tokens
        return {t: self._cache[t] for t in texts}
