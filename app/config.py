import os

from dotenv import load_dotenv

load_dotenv()

# "openrouter" or "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()

# OpenRouter (OpenAI-compatible API, many models)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-5.5")

OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
# Semantic skill matching in /screen (embeddings via OpenRouter + LLM verification)
SEMANTIC_MATCHING = os.getenv("SEMANTIC_MATCHING", "true").lower() == "true"

# Anthropic direct
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "low")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))

# Protects the LLM budget of a public demo (see app/core/rate_limit.py)
# Counted in LLM calls; a 10-resume screen with semantic matching can use up to 21.
RATE_LIMIT_PER_IP_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_IP_PER_HOUR", "50"))
RATE_LIMIT_GLOBAL_PER_DAY = int(os.getenv("RATE_LIMIT_GLOBAL_PER_DAY", "1000"))
