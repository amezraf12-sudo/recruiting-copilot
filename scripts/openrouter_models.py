"""List OpenRouter models that support structured outputs, with prices.

No API key needed. Usage, from the project root:
    python -m scripts.openrouter_models            # all, cheapest first
    python -m scripts.openrouter_models anthropic  # filter by text in the id
"""

import sys

import httpx

from app import config

URL = "https://openrouter.ai/api/v1/models"


def per_million(price: str | None) -> float:
    return float(price or 0) * 1_000_000


def main() -> None:
    resp = httpx.get(URL, params={"supported_parameters": "structured_outputs"}, timeout=30)
    resp.raise_for_status()
    models = resp.json()["data"]

    query = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    rows = sorted(
        (
            (m["id"], per_million(m["pricing"].get("prompt")), per_million(m["pricing"].get("completion")),
             m.get("context_length"))
            for m in models
            if query in m["id"].lower()
        ),
        key=lambda r: (r[1] + r[2], r[0]),
    )

    print(f"{'model id':55} {'$/1M in':>9} {'$/1M out':>9} {'context':>9}")
    for model_id, p_in, p_out, ctx in rows:
        print(f"{model_id:55} {p_in:9.2f} {p_out:9.2f} {ctx or 0:9}")

    configured = config.OPENROUTER_MODEL
    ok = any(m["id"] == configured for m in models)
    print(f"\nConfigured OPENROUTER_MODEL={configured}: "
          f"{'supports structured outputs' if ok else 'NOT FOUND with structured outputs'}")


if __name__ == "__main__":
    main()
