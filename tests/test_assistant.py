"""Recruiter assistant: agent loop, tools, guardrails and API, with a scripted fake model."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletion

from app.core.deps import get_chat_client
from app.core.rate_limit import RateLimiter, get_limiter
from app.domains.recruiting.assistant import MAX_STEPS, run_assistant
from app.domains.recruiting.guardrails import check_draft
from app.domains.recruiting.matching import score_candidate
from app.domains.recruiting.schemas import AssistantRequest, ChatMessage
from app.main import app
from tests.factories import job, parsed, profile

JOB = job(must=["React", "Node.js"], min_years=3, seniority="senior",
          flagged_requirements=["Female", "25-35 years old"])
MARIA = score_candidate("maria", parsed(profile("Maria Santos", technical=["React", "Node.js"])), JOB)
AISHA = score_candidate("aisha", parsed(profile("Aisha Rahman", technical=["React"])), JOB)


def completion(*, content=None, calls=()) -> ChatCompletion:
    """A real SDK ChatCompletion: either tool calls or a final text reply."""
    tool_calls = [{"id": f"call_{i}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}}
                  for i, (name, args) in enumerate(calls)]
    return ChatCompletion.model_validate({
        "id": "c", "object": "chat.completion", "created": 0, "model": "fake",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop",
                     "message": {"role": "assistant", "content": content,
                                 **({"tool_calls": tool_calls} if tool_calls else {})}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    })


class FakeChat:
    """Plays back scripted completions and records every request it receives."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        return self.script.pop(0)

    async def close(self):
        pass


def request(text="Draft outreach for Aisha") -> AssistantRequest:
    return AssistantRequest(job=JOB, candidates=[MARIA, AISHA],
                            messages=[ChatMessage(role="user", content=text)])


def run(fake, req=None, on_step=None):
    return asyncio.run(run_assistant(fake, req or request(), on_step=on_step))


def tool_result(fake, call_index=-1) -> dict:
    """The tool message content the model saw on its last request."""
    tool_messages = [m for m in fake.requests[-1] if m["role"] == "tool"]
    return json.loads(tool_messages[call_index]["content"])


def test_agent_looks_up_then_proposes_and_nothing_is_sent():
    fake = FakeChat(
        completion(calls=[("get_candidate", {"candidate_id": "aisha"})]),
        completion(calls=[("propose_outreach_email", {
            "candidate_id": "aisha", "subject": "Full-stack role",
            "body": "Hi Aisha, your React work stood out. Could we talk about Node.js?"})]),
        completion(content="I drafted an outreach email for Aisha for your review."),
    )
    result = run(fake)
    assert [t.tool for t in result.trace] == ["get_candidate", "propose_outreach_email"]
    assert all(t.ok for t in result.trace)
    [action] = result.actions
    assert (action.type, action.candidate_name, action.warnings) == ("outreach_email", "Aisha Rahman", [])
    assert "drafted" in result.reply and result.usage.llm_calls == 3
    candidate_data = json.loads(fake.requests[1][-1]["content"])
    assert candidate_data["missing_required"] == ["Node.js"]
    assert "email" not in json.dumps(candidate_data["untrusted_resume_data"])  # no contact details


def test_guardrail_warnings_are_attached_to_risky_drafts():
    fake = FakeChat(
        completion(calls=[("propose_screening_questions", {
            "candidate_id": "maria",
            "questions": ["As a woman in tech, how do you handle pressure?",
                          "You scored 92/100; why?"]})]),
        completion(content="Done."),
    )
    [action] = run(fake).actions
    assert any("gender" in w for w in action.warnings)
    assert any("internal score" in w for w in action.warnings)
    assert tool_result(fake)["guardrail_warnings"] == action.warnings  # model sees them too


def test_job_tool_never_exposes_flagged_requirements():
    fake = FakeChat(completion(calls=[("get_job", {})]), completion(content="ok"))
    run(fake)
    job_seen = tool_result(fake)
    assert "flagged_requirements" not in job_seen
    assert "Female" not in json.dumps(job_seen)
    assert job_seen["flagged_requirements_excluded"] == 2


@pytest.mark.parametrize("name,args,error", [
    ("get_candidate", {"candidate_id": "nobody"}, "Unknown candidate_id"),
    ("propose_screening_questions", {"candidate_id": "maria", "questions": []}, "at least 1"),
    ("send_email", {"to": "x"}, "Unknown tool"),
])
def test_bad_tool_calls_return_errors_the_model_can_recover_from(name, args, error):
    fake = FakeChat(completion(calls=[(name, args)]), completion(content="Sorry, fixing that."))
    result = run(fake)
    assert error in tool_result(fake)["error"]
    assert result.trace[0].ok is False and result.actions == []


def test_loop_stops_after_max_steps():
    fake = FakeChat(*[completion(calls=[("list_candidates", {})]) for _ in range(MAX_STEPS)])
    result = run(fake)
    assert result.usage.llm_calls == MAX_STEPS and "stopped" in result.reply


def test_every_step_after_the_first_is_charged():
    fake = FakeChat(completion(calls=[("list_candidates", {})]),
                    completion(calls=[("get_job", {})]), completion(content="ok"))
    charged = []
    run(fake, on_step=charged.append)
    assert charged == [2, 3]


@pytest.mark.parametrize("text,expected", [
    ("Led a single sign-on migration for the management team.", []),
    ("We'd love to discuss the role; are you available Tuesday?", []),
    ("Must be 25 years old and single, please send a photo.", ["age", "appearance"]),
])
def test_guardrail_flags_protected_language_without_common_false_positives(text, expected):
    found = check_draft(text)
    assert [label for label in expected if any(label in w for w in found)] == expected
    assert len(found) == len(expected)


# --- API ---

@pytest.fixture
def api():
    def _make(fake, limiter=None):
        app.dependency_overrides[get_chat_client] = lambda: fake
        app.dependency_overrides[get_limiter] = lambda: limiter or RateLimiter(1000, 1000)
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def body(messages=None):
    return {"job": JOB.model_dump(), "candidates": [MARIA.model_dump(), AISHA.model_dump()],
            "messages": messages or [{"role": "user", "content": "Who should I call first?"}]}


def test_api_returns_reply_actions_and_trace(api):
    fake = FakeChat(completion(calls=[("list_candidates", {})]),
                    completion(content="Call Maria first: she has every required skill."))
    resp = api(fake).post("/recruiting/assistant", json=body())
    assert resp.status_code == 200
    assert resp.json()["trace"][0]["tool"] == "list_candidates"


def test_api_rate_limits_agent_steps_as_they_happen(api):
    fake = FakeChat(completion(calls=[("list_candidates", {})]), completion(content="ok"))
    resp = api(fake, RateLimiter(per_ip_per_hour=1, global_per_day=100)).post(
        "/recruiting/assistant", json=body())
    assert resp.status_code == 429  # step 1 allowed by the router, step 2 over the limit


def test_api_needs_a_tool_calling_provider(api):
    assert api(None).post("/recruiting/assistant", json=body()).status_code == 501


def test_api_requires_conversation_to_end_with_user(api):
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert api(FakeChat()).post("/recruiting/assistant", json=body(msgs)).status_code == 422
