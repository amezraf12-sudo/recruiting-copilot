"""Skill normalization and matching between job requirements and candidate profiles."""

import re

from app.domains.recruiting.schemas import ResumeExtraction

# Common spellings -> one canonical key. Keys and values are already normalized (see _key).
_ALIASES = {
    "postgres": "postgresql",
    "psql": "postgresql",
    "js": "javascript",
    "ecmascript": "javascript",
    "ts": "typescript",
    "golang": "go",
    "k8s": "kubernetes",
    "reactjs": "react",
    "vuejs": "vue",
    "angularjs": "angular",
    "node": "nodejs",
    "amazonwebservices": "aws",
    "gcp": "googlecloud",
    "googlecloudplatform": "googlecloud",
    "msazure": "azure",
    "microsoftazure": "azure",
    "mongo": "mongodb",
    "scikit": "scikitlearn",
    "sklearn": "scikitlearn",
    "tailwind": "tailwindcss",
}


# Trailing words that describe what a skill is rather than which skill it is. Seen in a
# screening eval: a job asked for "Greenhouse ATS" and the resume said "Greenhouse".
_GENERIC_SUFFIXES = {"ats", "framework", "library", "platform", "language", "database"}


def _key(skill: str) -> str:
    s = skill.lower().replace("+", "plus").replace("#", "sharp")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w]
    if len(words) > 1 and words[-1] in _GENERIC_SUFFIXES:
        words = words[:-1]
    s = "".join(words)
    return _ALIASES.get(s, s)


def skill_key(skill: str) -> str:
    """Canonical comparison key: 'Postgres', 'PostgreSQL' and 'postgresql' all match."""
    return _key(skill)


def candidate_skill_keys(profile: ResumeExtraction) -> set[str]:
    return {skill_key(s) for s in profile.technical_skills + profile.soft_skills if s.strip()}


def _mentioned_in(text: str, skill: str) -> bool:
    # Whole-word match, so "Go" doesn't match "Google" and "Java" doesn't match "JavaScript".
    return re.search(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])", text) is not None


def candidate_phrases(profile: ResumeExtraction) -> list[str]:
    """Everything a skill could be demonstrated by: skills, headline, titles, highlights."""
    phrases = (
        profile.technical_skills + profile.soft_skills + [profile.headline]
        + [p.title for p in profile.experience]
        + [h for p in profile.experience for h in p.highlights]
    )
    return list(dict.fromkeys(p.strip() for p in phrases if p and p.strip()))


def exact_match(skill: str, phrase: str) -> bool:
    """Same skill by canonical key, or the skill named as a whole word inside the phrase."""
    return skill_key(skill) == skill_key(phrase) or _mentioned_in(phrase.lower(), skill)


def has_skill(profile: ResumeExtraction, skill: str, keys: set[str] | None = None) -> bool:
    """True if the skill is in the profile's skill lists or named in its experience."""
    keys = candidate_skill_keys(profile) if keys is None else keys
    if skill_key(skill) in keys:
        return True
    experience_text = " ".join(
        [p.title for p in profile.experience]
        + [h for p in profile.experience for h in p.highlights]
    ).lower()
    return _mentioned_in(experience_text, skill)
