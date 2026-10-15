import os

from dotenv import load_dotenv

load_dotenv()

# "openrouter" or "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()

# OpenRouter (OpenAI-compatible API, many models)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-5.5")

# Anthropic direct
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "low")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
