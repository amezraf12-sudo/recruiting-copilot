"""API tests with a fake extractor: fast, free, and no API key needed."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.deps import get_extractor
from app.core.errors import LLMRefusalError
from app.core.llm import ExtractionResult
from app.core.rate_limit import RateLimiter, client_ip, rate_limit
from app.core.schemas import UsageInfo
from app.domains.recruiting.schemas import ResumeExtraction, SenioritySignals, WorkExperience
from app.main import app

RESUME_TEXT = "Maria Santos - Senior Full-Stack Developer, TalentBridge PH, Jan 2022 to Present. " * 2

FAKE_PROFILE = ResumeExtraction(
    full_name="Maria Santos",
    email="maria@example.com",
    phone=None,
    location="Manila, Philippines",
    links=[],
    headline="Senior full-stack developer.",
    seniority_signals=SenioritySignals(
        is_student=False, has_senior_title=True, owns_outcomes=True, leads_team=False,
        org_level_scope=False, evidence=["Senior Full-Stack Developer"],
    ),
    technical_skills=["React", "Node.js"],
    soft_skills=[],
    experience=[
        WorkExperience(
            company="TalentBridge PH", title="Senior Full-Stack Developer",
            start_date="2022-01", end_date=None, is_current=True, highlights=[],
        ),
        WorkExperience(
            company="Manila Digital Works", title="Full-Stack Developer",
            start_date="2019-06", end_date="2021-12", is_current=False, highlights=[],
        ),
    ],
    education=[],
    certifications=[],
    languages=["English", "Filipino"],
)


class FakeExtractor:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []

    async def extract(self, **kwargs) -> ExtractionResult:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return ExtractionResult(
            data=FAKE_PROFILE,
            usage=UsageInfo(model="fake", input_tokens=10, output_tokens=20, latency_ms=5),
        )


@pytest.fixture
def client_with():
    def _make(extractor, limiter: RateLimiter | None = None):
        app.dependency_overrides[get_extractor] = lambda: extractor
        # Rate limiting is tested on its own; other tests get a fresh, generous limiter.
        fresh = limiter or RateLimiter(per_ip_per_hour=1000, global_per_day=1000)

        def limited(request: Request) -> None:
            fresh.check(client_ip(request))

        app.dependency_overrides[rate_limit] = limited
        return TestClient(app)  # no `with` -> lifespan (real client) doesn't start

    yield _make
    app.dependency_overrides.clear()


def test_health(client_with):
    assert client_with(FakeExtractor()).get("/health").json() == {"status": "ok"}


def test_root_redirects_to_docs(client_with):
    resp = client_with(FakeExtractor()).get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/docs"


def test_rate_limit_returns_429_and_skips_llm(client_with):
    fake = FakeExtractor()
    client = client_with(fake, RateLimiter(per_ip_per_hour=2, global_per_day=100))
    codes = [client.post("/recruiting/parse-resume", json={"text": RESUME_TEXT}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    assert len(fake.calls) == 2  # the blocked request never reached the LLM


def test_parse_text_returns_profile_and_computed_years(client_with):
    fake = FakeExtractor()
    resp = client_with(fake).post("/recruiting/parse-resume", json={"text": RESUME_TEXT})
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["full_name"] == "Maria Santos"
    assert body["total_years_experience"] > 7  # 2019-06 through today, computed in code
    assert body["seniority"] == "senior"  # computed in code from signals + years
    assert fake.calls[0]["text"] == RESUME_TEXT


@pytest.mark.parametrize("text", ["", "too short", "x" * 50_001], ids=["empty", "short", "too-long"])
def test_parse_text_rejects_bad_input(client_with, text):
    fake = FakeExtractor()
    resp = client_with(fake).post("/recruiting/parse-resume", json={"text": text})
    assert resp.status_code == 422
    assert fake.calls == []  # never reached the LLM


def test_upload_pdf_is_sent_as_pdf(client_with):
    fake = FakeExtractor()
    pdf = b"%PDF-1.7 fake pdf bytes"
    resp = client_with(fake).post(
        "/recruiting/parse-resume/file", files={"file": ("cv.pdf", pdf, "application/pdf")}
    )
    assert resp.status_code == 200
    assert fake.calls[0]["pdf"] == pdf


def test_upload_txt_is_sent_as_text(client_with):
    fake = FakeExtractor()
    resp = client_with(fake).post(
        "/recruiting/parse-resume/file",
        files={"file": ("cv.txt", RESUME_TEXT.encode(), "text/plain")},
    )
    assert resp.status_code == 200
    assert fake.calls[0]["text"] == RESUME_TEXT


def test_upload_rejects_other_types(client_with):
    fake = FakeExtractor()
    resp = client_with(fake).post(
        "/recruiting/parse-resume/file", files={"file": ("cv.docx", b"PK\x03\x04", "application/zip")}
    )
    assert resp.status_code == 415
    assert fake.calls == []


def test_upload_rejects_oversized_files(client_with, monkeypatch):
    monkeypatch.setattr("app.config.MAX_UPLOAD_BYTES", 10)
    resp = client_with(FakeExtractor()).post(
        "/recruiting/parse-resume/file", files={"file": ("cv.pdf", b"%PDF" + b"x" * 20, "application/pdf")}
    )
    assert resp.status_code == 413


def test_refusal_maps_to_422(client_with):
    resp = client_with(FakeExtractor(LLMRefusalError("declined"))).post(
        "/recruiting/parse-resume", json={"text": RESUME_TEXT}
    )
    assert resp.status_code == 422
