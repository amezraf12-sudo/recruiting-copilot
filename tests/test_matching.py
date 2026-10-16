from app.domains.recruiting.matching import rank, score_candidate
from tests.factories import job, parsed, profile


def test_perfect_match_scores_100():
    m = score_candidate(
        "a", parsed(profile(technical=["Go", "PostgreSQL", "Redis"]), years=6, seniority="senior"),
        job(must=["Go", "PostgreSQL"], nice=["Redis"], min_years=5, seniority="senior"),
    )
    assert m.score == 100
    assert m.meets_all_must_haves and m.missing_must_haves == []
    assert m.matched_nice_to_haves == ["Redis"]


def test_missing_must_have_is_reported_and_lowers_score():
    m = score_candidate(
        "a", parsed(profile(technical=["Go"])), job(must=["Go", "Kubernetes"]),
    )
    assert not m.meets_all_must_haves
    assert m.missing_must_haves == ["Kubernetes"]
    assert m.score == 50  # only the must-have component applies: 1 of 2
    assert any("Missing required: Kubernetes" in r for r in m.reasons)


def test_years_below_minimum_get_partial_credit():
    m = score_candidate("a", parsed(profile(), years=2.5), job(min_years=5))
    assert m.score == 50
    assert any("below" in r for r in m.reasons)


def test_seniority_one_level_off_gets_half_credit():
    m = score_candidate("a", parsed(profile(), seniority="mid"), job(seniority="senior"))
    assert m.score == 50


def test_job_with_no_criteria_scores_zero_not_error():
    assert score_candidate("a", parsed(profile()), job()).score == 0


def test_identity_does_not_change_score():
    # Fairness: same skills and experience, different name/school -> identical score.
    requirements = job(must=["React", "Node.js"], min_years=3, seniority="senior")
    a = profile(name="Maria Santos", technical=["React", "Node.js"])
    b = profile(name="John Smith", technical=["React", "Node.js"], education=[{
        "institution": "Harvard University", "degree": "BS", "field_of_study": "CS",
        "graduation_year": 2015,
    }])
    assert score_candidate("a", parsed(a), requirements).score == \
        score_candidate("b", parsed(b), requirements).score


def test_unrelated_experience_earns_nothing():
    # Seen in a screening run: a senior recruiter scored 35/100 for a developer job.
    recruiter = parsed(profile(technical=["Boolean search", "Greenhouse"]), years=8.4)
    m = score_candidate("p", recruiter, job(must=["React", "Node.js"], min_years=5, seniority="senior"))
    assert m.score == 0


def test_experience_credit_scales_with_required_skill_coverage():
    half = parsed(profile(technical=["React"]), years=10, seniority="senior")
    m = score_candidate("a", half, job(must=["React", "Node.js"], min_years=5, seniority="senior"))
    assert m.score == 50  # every component at 50%: half the skills, experience credited at 50%
    assert any("credited at 50%" in r for r in m.reasons)


def test_bonus_skills_earn_nothing_without_required_skills():
    m = score_candidate("d", parsed(profile(technical=["Docker"])), job(must=["React"], nice=["Docker"]))
    assert m.score == 0


def test_rank_breaks_score_ties_in_favor_of_complete_must_haves():
    requirements = job(must=["Go", "Kubernetes"], nice=["Redis", "Kafka", "gRPC"], min_years=5,
                       seniority="senior")
    complete = score_candidate(
        "complete", parsed(profile(technical=["Go", "Kubernetes"]), years=0, seniority="junior"),
        requirements,
    )
    partial = score_candidate(
        "partial", parsed(profile(technical=["Go", "Redis", "Kafka", "gRPC"]), years=10),
        requirements,
    )
    assert partial.score == complete.score == 50
    assert [m.candidate_id for m in rank([partial, complete])] == ["complete", "partial"]
