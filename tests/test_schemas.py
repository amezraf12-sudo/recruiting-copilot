from app.domains.recruiting.schemas import ResumeExtraction, SenioritySignals


def profile(email, links=None, phone=None) -> ResumeExtraction:
    return ResumeExtraction(
        full_name="Liza Moreno", email=email, phone=phone, location=None, links=links or [],
        headline="Designer.",
        seniority_signals=SenioritySignals(
            is_student=False, has_senior_title=False, owns_outcomes=False, leads_team=False,
            org_level_scope=False, evidence=[],
        ),
        technical_skills=[], soft_skills=[], experience=[], education=[], certifications=[],
        languages=[],
    )


def test_valid_email_is_kept():
    assert profile("liza@example.com").email == "liza@example.com"


def test_non_email_moves_to_links():
    p = profile("lizamoreno.design")
    assert p.email is None
    assert p.links == ["lizamoreno.design"]


def test_blank_strings_become_none():
    p = profile("  ", phone="")
    assert p.email is None and p.phone is None
    assert p.links == []  # blank email is not a link


def test_non_email_not_duplicated_in_links():
    p = profile("lizamoreno.design", links=["lizamoreno.design"])
    assert p.links == ["lizamoreno.design"]
