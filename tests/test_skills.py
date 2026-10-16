import pytest

from app.domains.recruiting.skills import has_skill, skill_key
from tests.factories import profile


@pytest.mark.parametrize(
    "a,b",
    [("PostgreSQL", "postgres"), ("Node.js", "NodeJS"), ("Next.js", "nextjs"), ("Go", "Golang"),
     ("Kubernetes", "k8s"), ("React", "React.js"), ("scikit-learn", "sklearn"), ("AWS", "aws"),
     ("Greenhouse ATS", "Greenhouse"), ("Django framework", "Django"), ("Google Cloud Platform", "GCP")],
)
def test_aliases_share_a_key(a, b):
    assert skill_key(a) == skill_key(b)


@pytest.mark.parametrize(
    "a,b", [("C++", "C"), ("C#", "C"), ("Java", "JavaScript"), ("Stats", "St"), ("ATS", "")]
)
def test_different_skills_stay_different(a, b):
    assert skill_key(a) != skill_key(b)


def test_skill_found_in_skill_list():
    assert has_skill(profile(technical=["postgres"]), "PostgreSQL")


def test_skill_found_in_experience_highlights():
    p = profile(highlights=["Migrated services to Kubernetes"])
    assert has_skill(p, "Kubernetes")


@pytest.mark.parametrize(
    "highlight,skill",
    [("Interned at Google", "Go"), ("Built JavaScript apps", "Java"), ("Wrote Reactive code", "React")],
)
def test_no_false_matches_inside_other_words(highlight, skill):
    assert not has_skill(profile(highlights=[highlight]), skill)
