"""Deterministic checks on assistant drafts before a recruiter sees them.

The prompt tells the model not to mention protected attributes or internal scores; this
code checks that it didn't. Findings become warnings on the proposal (the recruiter
decides), not silent edits.
"""

import re

_CHECKS: list[tuple[str, re.Pattern]] = [
    ("age", re.compile(r"\byears? old\b|\bage\b|\bbirth(?:day|date)?\b|\b(?:young|younger|older)\b", re.I)),
    ("gender", re.compile(r"\b(?:female|male|gender|woman|women|ladies)\b", re.I)),
    ("civil status / family", re.compile(r"\bcivil status\b|\bmarital\b|\bmarried\b|\bpregnan\w*|\bchildren\b", re.I)),
    ("religion", re.compile(r"\breligio\w*|\bcatholic\b|\bchristian\b|\bmuslim\b|\bchurch\b", re.I)),
    ("appearance", re.compile(
        r"\bheight\b|\bweight\b|\bpleasing personality\b|\bpresentable\b|\bgood[- ]looking\b"
        r"|\battractive\b|\bphoto\b", re.I)),
    ("internal score", re.compile(r"\b\d{1,3}\s*/\s*100\b|\bscore[sd]?\b|\branked\b|\branking\b", re.I)),
]


def check_draft(*texts: str) -> list[str]:
    """Warnings for protected-attribute language or internal scores in a draft."""
    joined = "\n".join(t for t in texts if t)
    warnings = []
    for label, pattern in _CHECKS:
        found = sorted({m.group(0).lower() for m in pattern.finditer(joined)})
        if found:
            warnings.append(f"Mentions {label}: {', '.join(found)}. Review before sending.")
    return warnings
