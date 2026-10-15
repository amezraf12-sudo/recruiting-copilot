import pytest

from app.domains.recruiting.schemas import SenioritySignals
from app.domains.recruiting.seniority import infer_seniority


def signals(**true_flags) -> SenioritySignals:
    flags = dict.fromkeys(
        ["is_student", "has_senior_title", "owns_outcomes", "leads_team", "org_level_scope"], False
    )
    return SenioritySignals(**(flags | true_flags), evidence=[])


@pytest.mark.parametrize(
    "flags,years,expected",
    [
        # eval cases that every model rated "mid": ownership + 5 years is senior
        ({"owns_outcomes": True}, 6.67, "senior"),   # Aisha: owns payments service
        ({"owns_outcomes": True}, 5.75, "senior"),   # Liza: maintains design system
        ({"has_senior_title": True}, 3.0, "senior"),
        ({"has_senior_title": True}, 2.5, "mid"),    # title alone needs 3+ years
        ({"owns_outcomes": True}, 4.9, "mid"),       # ownership alone needs 5+ years
        ({}, 9.0, "mid"),                            # long tenure, no ownership signal
        ({}, 1.83, "junior"),                        # Mark
        ({}, 0.25, "junior"),                        # Juan: graduate, internship only
        ({"is_student": True}, 0.25, "intern"),
        ({"leads_team": True}, 8.83, "lead"),        # Kevin
        ({"leads_team": True, "org_level_scope": True}, 12, "principal"),
        ({"leads_team": True, "is_student": True}, 1, "lead"),
    ],
)
def test_infer_seniority(flags, years, expected):
    assert infer_seniority(signals(**flags), years) == expected
