"""Stage 3 of agentic matching: a bounded LangGraph tool-calling loop over the
shortlist produced by matcher.py (Stage 1, zero-cost heuristic) + embedder.py
(Stage 2, cheap semantic re-rank).

This is the layer that makes the resume's "ranking each posting against a
resume with LLMs" claim true — score_match is a real reasoned LLM call, and
the agent (not fixed code) decides which postings to score, whether to draft
a bullet for them, and whether the shortlist is weak enough to search again.

Built as an explicit LangGraph StateGraph (not a bare while-loop) so the
control flow — model turn -> tool turn -> model turn, with a hard exit once
`finish` is called or the iteration budget runs out — is a graph you can point
to, not implicit in a chain of if-statements. Cost is bounded by construction:
this graph only ever runs over the shortlist (a handful of postings, not the
100+ fetched per run), and MAX_ITERATIONS caps the worst case even if the
model tries to loop indefinitely.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
_MODEL = "llama-3.3-70b-versatile"

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "score_match",
            "description": (
                "Produce a reasoned 0-1 match score and a short rationale for one "
                "posting from the shortlist, comparing it against the candidate's profile."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "id of a posting from the shortlist",
                    },
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_bullet",
            "description": (
                "Draft a one-sentence match rationale for a posting that scored well, to "
                "show the candidate why it's a strong fit. Only call this AFTER "
                "score_match for that job_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_job_board",
            "description": (
                "Broaden the search with a different query if the current shortlist looks weak "
                "(e.g. too few strong matches). Returns additional candidate postings, which get "
                "added to the pool. Use sparingly — only when genuinely needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "a broader or differently-worded search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "Call when you've scored the postings worth scoring and drafted bullets "
                "for the good ones. Ends the run."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


@dataclass
class AgentResult:
    scores: dict[str, dict] = field(default_factory=dict)  # job_id -> {score, rationale}
    drafts: dict[str, str] = field(default_factory=dict)  # job_id -> bullet
    extra_jobs: list[dict] = field(default_factory=list)  # postings pulled in via search_job_board
    iterations_used: int = 0
    # finished | max_iterations | no_budget | no_api_key | api_error
    stopped_reason: str = "finished"


class AgentState(TypedDict):
    messages: list[dict]
    job_pool: dict[str, dict]
    result: AgentResult
    iteration: int
    max_iterations: int
    finished: bool
    client: object
    search_fn: object | None
    profile: dict


def _shortlist_summary(shortlist: list[dict]) -> str:
    lines = []
    for j in shortlist:
        desc = (j.get("raw_description") or "")[:400]
        lines.append(f"- id={j['id']} | {j['title']} @ {j['company']}\n  {desc}")
    return "\n".join(lines)


def _profile_summary(profile: dict) -> str:
    parsed = profile.get("parsed_experience") or {}
    bullets = parsed.get("experience_bullets") or []
    skills = profile.get("skills") or []
    return (
        f"Headline: {profile.get('headline')}\n"
        f"Years experience: {profile.get('years_experience')}\n"
        f"Skills: {', '.join(skills)}\n"
        f"Experience:\n" + "\n".join(f"- {b}" for b in bullets)
    )


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def _call_model(state: AgentState) -> dict:
    client = state["client"]
    messages = state["messages"]
    response = _call_with_retry(client, messages)
    if response is None:
        state["result"].stopped_reason = "api_error"
        return {"messages": messages, "finished": True}

    msg = response.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None)
    new_messages = messages + [
        {"role": "assistant", "content": msg.content or "", "tool_calls": tool_calls}
    ]
    return {"messages": new_messages, "iteration": state["iteration"] + 1}


def _call_tools(state: AgentState) -> dict:
    messages = state["messages"]
    last = messages[-1]
    tool_calls = last.get("tool_calls") or []
    job_pool = state["job_pool"]
    result = state["result"]
    client = state["client"]
    profile = state["profile"]
    search_fn = state["search_fn"]

    finished = False
    new_messages = list(messages)
    for call in tool_calls:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}

        if name == "finish":
            finished = True
            tool_output = "run finished"
        elif name == "score_match":
            tool_output = _do_score_match(client, job_pool, profile, args.get("job_id"), result)
        elif name == "draft_bullet":
            tool_output = _do_draft_bullet(client, job_pool, args.get("job_id"), result)
        elif name == "search_job_board":
            tool_output = _do_search(search_fn, job_pool, args.get("query"), result)
        else:
            tool_output = f"unknown tool {name}"

        new_messages.append({"role": "tool", "tool_call_id": call.id, "content": tool_output})

    return {"messages": new_messages, "finished": finished, "job_pool": job_pool}


def _route_after_model(state: AgentState) -> str:
    last = state["messages"][-1]
    if state.get("finished"):
        return END
    if not last.get("tool_calls"):
        state["result"].stopped_reason = "finished"
        return END
    return "tools"


def _route_after_tools(state: AgentState) -> str:
    if state.get("finished"):
        state["result"].stopped_reason = "finished"
        return END
    if state["iteration"] >= state["max_iterations"]:
        state["result"].stopped_reason = "max_iterations"
        return END
    return "agent"


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", _call_model)
    graph.add_node("tools", _call_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route_after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", _route_after_tools, {"agent": "agent", END: END})
    return graph.compile()


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_agent(
    profile: dict,
    shortlist: list[dict],
    search_fn: Callable[[str], list[dict]] | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> AgentResult:
    """profile: dict with headline/years_experience/skills/parsed_experience.
    shortlist: list of {id, title, company, raw_description} — the Stage 1+2 output.
    search_fn: optional callable(query) -> list of the same shape, wired by the
    caller (orchestrator.py) to the real fetch pipeline. If None, the
    search_job_board tool is a no-op (returns nothing new)."""
    result = AgentResult()

    if not settings.groq_api_key:
        logger.info("agent: no groq_api_key configured, skipping agentic scoring")
        result.stopped_reason = "no_api_key"
        return result
    if not shortlist:
        result.stopped_reason = "finished"
        return result

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    job_pool: dict[str, dict] = {j["id"]: j for j in shortlist}

    system_prompt = (
        "You are a job-matching agent. Goal: find and evaluate the best-matching postings "
        "for this candidate from the shortlist below, calling tools to score and draft "
        "rationale for the genuinely strong matches. Don't score every posting if some are "
        "obviously irrelevant. Call finish when done.\n\n"
        f"CANDIDATE PROFILE:\n{_profile_summary(profile)}\n\n"
        f"SHORTLIST:\n{_shortlist_summary(shortlist)}"
    )
    initial_state: AgentState = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Evaluate the shortlist now."},
        ],
        "job_pool": job_pool,
        "result": result,
        "iteration": 0,
        "max_iterations": max_iterations,
        "finished": False,
        "client": client,
        "search_fn": search_fn,
        "profile": profile,
    }

    graph = _get_graph()
    final_state = graph.invoke(initial_state)
    result.iterations_used = final_state["iteration"]
    return result


def _call_with_retry(client, messages: list[dict]):
    for attempt in range(3):
        try:
            return client.chat.completions.create(
                model=_MODEL,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=2048,
            )
        except Exception as exc:  # RateLimitError from groq, or transient errors
            if attempt == 2:
                logger.warning("agent: Groq call failed after retries (%s)", exc)
                return None
            wait = 5 * (2 ** attempt)
            logger.warning(
                "agent: Groq error, retry in %ds (attempt %d/2): %s", wait, attempt + 1, exc
            )
            time.sleep(wait)
    return None


def _do_score_match(
    client, job_pool: dict, profile: dict, job_id: str | None, result: AgentResult
) -> str:
    job = job_pool.get(job_id) if job_id else None
    if not job:
        return f"error: unknown job_id {job_id!r}"

    prompt = (
        "Score this candidate against this posting on a 0-1 scale and give a "
        "one-sentence rationale.\n"
        "Return ONLY JSON: {\"score\": 0.0-1.0, \"rationale\": \"...\"}\n\n"
        f"CANDIDATE:\n{_profile_summary(profile)}\n\n"
        f"POSTING: {job['title']} @ {job['company']}\n{(job.get('raw_description') or '')[:2000]}"
    )
    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        result.scores[job_id] = {
            "score": float(data.get("score", 0)),
            "rationale": data.get("rationale", ""),
        }
        return json.dumps(result.scores[job_id])
    except Exception as exc:
        logger.warning("agent: score_match failed for %s: %s", job_id, exc)
        return f"error scoring {job_id}: {exc}"


def _do_draft_bullet(client, job_pool: dict, job_id: str | None, result: AgentResult) -> str:
    job = job_pool.get(job_id) if job_id else None
    if not job:
        return f"error: unknown job_id {job_id!r}"
    if job_id not in result.scores:
        return "error: call score_match for this job_id first"

    prompt = (
        f"In one sentence, explain why this candidate is a strong fit for this posting "
        f"(no invented facts, only what's true from the profile).\n\n"
        f"Rationale so far: {result.scores[job_id]['rationale']}\n"
        f"Posting: {job['title']} @ {job['company']}"
    )
    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        bullet = resp.choices[0].message.content.strip()
        result.drafts[job_id] = bullet
        return bullet
    except Exception as exc:
        logger.warning("agent: draft_bullet failed for %s: %s", job_id, exc)
        return f"error drafting for {job_id}: {exc}"


def _do_search(search_fn, job_pool: dict, query: str | None, result: AgentResult) -> str:
    if not search_fn or not query:
        return "search unavailable in this context"
    try:
        new_jobs = search_fn(query) or []
    except Exception as exc:
        logger.warning("agent: search_job_board failed: %s", exc)
        return f"search failed: {exc}"

    added = 0
    for j in new_jobs:
        if j["id"] not in job_pool:
            job_pool[j["id"]] = j
            result.extra_jobs.append(j)
            added += 1
    return f"found {len(new_jobs)} results, added {added} new postings to the pool"
