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


def _key(skill: str) -> str:
    s = skill.lower().replace("+", "plus").replace("#", "sharp")
    s = re.sub(r"[^a-z0-9]", "", s)
    return _ALIASES.get(s, s)


def skill_key(skill: str) -> str:
    """Canonical comparison key: 'Postgres', 'PostgreSQL' and 'postgresql' all match."""
    return _key(skill)


def candidate_skill_keys(profile: ResumeExtraction) -> set[str]:
    return {skill_key(s) for s in profile.technical_skills + profile.soft_skills if s.strip()}


def _mentioned_in(text: str, skill: str) -> bool:
    # Whole-word match, so "Go" doesn't match "Google" and "Java" doesn't match "JavaScript".
    return re.search(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])", text) is not None


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
