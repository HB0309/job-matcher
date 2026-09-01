import json
from unittest.mock import MagicMock

import app.workers.agent as agent


def test_run_agent_no_api_key_returns_empty_result(monkeypatch):
    monkeypatch.setattr("app.config.settings.groq_api_key", "")
    result = agent.run_agent(profile={"headline": "SWE"}, shortlist=[{"id": "A", "title": "x", "company": "y", "raw_description": "z"}])
    assert result.stopped_reason == "no_api_key"
    assert result.scores == {}


def test_run_agent_empty_shortlist_short_circuits(monkeypatch):
    monkeypatch.setattr("app.config.settings.groq_api_key", "fake-key")
    result = agent.run_agent(profile={"headline": "SWE"}, shortlist=[])
    assert result.stopped_reason == "finished"
    assert result.scores == {}


def _make_tool_call(name: str, args: dict, call_id: str = "call1"):
    call = MagicMock()
    call.id = call_id
    call.function = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(args)
    return call


def _make_response(content=None, tool_calls=None):
    resp = MagicMock()
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    resp.choices = [MagicMock(message=msg)]
    return resp


def test_run_agent_full_loop_score_then_finish(monkeypatch):
    """Agent decides to score one job, then finish — verifies the LangGraph
    loop actually routes agent -> tools -> agent -> END and that score_match's
    result lands in AgentResult.scores."""
    monkeypatch.setattr("app.config.settings.groq_api_key", "fake-key")

    call_count = {"n": 0}

    def fake_create(*, model, messages, tools=None, tool_choice=None, temperature=0.1, max_tokens=None):
        call_count["n"] += 1
        if tools is not None and call_count["n"] == 1:
            return _make_response(tool_calls=[_make_tool_call("score_match", {"job_id": "A"})])
        if tools is None and "Score this candidate" in messages[0]["content"]:
            return _make_response(content='{"score": 0.75, "rationale": "strong python overlap"}')
        if tools is not None:
            return _make_response(tool_calls=[_make_tool_call("finish", {})])
        return _make_response(content="done")

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr("groq.Groq", lambda api_key: fake_client)

    result = agent.run_agent(
        profile={"headline": "SWE", "years_experience": 1, "skills": ["python"], "parsed_experience": {"experience_bullets": ["built stuff"]}},
        shortlist=[{"id": "A", "title": "Backend Engineer", "company": "Acme", "raw_description": "python backend role"}],
    )

    assert result.stopped_reason == "finished"
    assert result.scores["A"]["score"] == 0.75
    assert result.iterations_used == 2


def test_run_agent_stops_at_max_iterations_if_model_never_finishes(monkeypatch):
    monkeypatch.setattr("app.config.settings.groq_api_key", "fake-key")

    def fake_create(*, model, messages, tools=None, tool_choice=None, temperature=0.1, max_tokens=None):
        # Always ask to score the same job, never call finish.
        if tools is not None:
            return _make_response(tool_calls=[_make_tool_call("score_match", {"job_id": "A"})])
        return _make_response(content='{"score": 0.5, "rationale": "ok"}')

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr("groq.Groq", lambda api_key: fake_client)

    result = agent.run_agent(
        profile={"headline": "SWE"},
        shortlist=[{"id": "A", "title": "x", "company": "y", "raw_description": "z"}],
        max_iterations=2,
    )

    assert result.stopped_reason == "max_iterations"
    assert result.iterations_used == 2
