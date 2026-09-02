import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Connector,
    FetchRun,
    FetchRunTarget,
    JobMatch,
    JobPosting,
    Profile,
    SourceTarget,
)
from app.schemas import FailedTarget, FetchJobsResponse
from app.workers import agent as agentic_matcher
from app.workers import embedder
from app.workers.connectors.base import JobQuery, RawJobPosting
from app.workers.deduper import dedupe
from app.workers.matcher import extract_domain_keywords, passes_title_filter, score_jobs
from app.workers.normalizer import NormalizedJob, normalize
from app.workers.registry import get_connector
from app.workers.run_metrics import StageMetrics
from app.workers.security_filter import filter_disqualifying_jobs
from app.workers.target_loader import load_enabled_targets

log = logging.getLogger(__name__)

# Stage 1->2 funnel sizes (see docs/03-agents-flows.md "Agentic matching funnel").
# Stage 1 (matcher.py heuristic) is zero-cost and already runs over every new
# posting; these two caps bound how many postings ever reach the paid stages.
_STAGE1_TOP_N = 20  # heuristic top-N handed to the embedding re-rank
_SHORTLIST_SIZE = 8  # embedding-re-ranked shortlist handed to the LLM agent


def _fetch_one(target, query: JobQuery) -> list[RawJobPosting]:
    connector = get_connector(target.connector_name)
    return connector.fetch_jobs(target, query)


def _profile_dict(profile: Profile) -> dict:
    return {
        "headline": profile.headline,
        "years_experience": profile.years_experience,
        "skills": profile.skills or [],
        "parsed_experience": profile.parsed_experience,
    }


def _profile_embedding_text(profile: Profile) -> str:
    parts = [profile.headline or "", ", ".join(profile.skills or [])]
    if profile.parsed_experience:
        parts.extend(profile.parsed_experience.get("experience_bullets") or [])
    return "\n".join(p for p in parts if p)


def _make_search_fn(
    new_jobs: list[NormalizedJob], job_key_to_posting: dict, already_shortlisted: set[str]
):
    """search_job_board tool implementation: re-filters postings already
    fetched THIS run (not a new live HTTP fetch — see plan discussion) by a
    keyword the agent supplies. Bounded, no external calls, lets the agent
    genuinely broaden its view beyond the top-N heuristic cut without the
    complexity/risk of a live re-fetch mid-agent-loop."""

    def search_fn(query: str) -> list[dict]:
        q = (query or "").lower()
        results = []
        for nj in new_jobs:
            jp = job_key_to_posting.get(f"{nj.source_target_id}:{nj.external_id}")
            if jp is None or jp.id in already_shortlisted:
                continue
            haystack = f"{nj.title} {nj.raw_description or ''}".lower()
            if q and q in haystack:
                results.append(
                    {
                        "id": jp.id,
                        "title": nj.title,
                        "company": nj.company,
                        "raw_description": nj.raw_description,
                    }
                )
            if len(results) >= 5:
                break
        return results

    return search_fn


def _run_agentic_stage(
    profile: Profile,
    new_jobs: list[NormalizedJob],
    scores: list[dict],
    job_key_to_posting: dict,
    match_by_job_id: dict[str, JobMatch],
    metrics: StageMetrics,
) -> None:
    """Stage 2 (embedding re-rank) + Stage 3 (LangGraph agent), bounded to a
    small shortlist. See docs/03-agents-flows.md for the funnel diagram and
    agent.py's module docstring for why this is what makes the "ranked with
    LLMs" claim true instead of aspirational."""
    if not new_jobs:
        return

    # Stage 1 cut: rank this run's heuristic scores, keep the top N.
    ranked = sorted(
        zip(new_jobs, scores), key=lambda pair: pair[1].get("overall", 0.0), reverse=True
    )
    top_n = ranked[:_STAGE1_TOP_N]
    postings_top_n = []
    for nj, _ in top_n:
        jp = job_key_to_posting.get(f"{nj.source_target_id}:{nj.external_id}")
        if jp is not None:
            postings_top_n.append((nj, jp))
    if not postings_top_n:
        return
    metrics.note("agentic_stage1_pool", len(postings_top_n))

    # Stage 2: semantic re-rank via cached embeddings. Degrades gracefully to
    # "just take the first _SHORTLIST_SIZE of the Stage 1 order" if the
    # profile has no embedding (e.g. no gemini_api_key configured).
    if profile.embedding is None:
        try:
            profile.embedding = embedder.embed_text(_profile_embedding_text(profile))
        except Exception:
            profile.embedding = None

    if profile.embedding:
        candidates = [(jp.id, jp.embedding) for _, jp in postings_top_n]
        shortlist_ids = embedder.rerank_by_similarity(
            profile.embedding, candidates, top_k=_SHORTLIST_SIZE
        )
    else:
        shortlist_ids = [jp.id for _, jp in postings_top_n[:_SHORTLIST_SIZE]]
    metrics.note("agentic_shortlist_size", len(shortlist_ids))

    id_to_pair = {jp.id: (nj, jp) for nj, jp in postings_top_n}
    shortlist = [
        {
            "id": jid,
            "title": id_to_pair[jid][0].title,
            "company": id_to_pair[jid][0].company,
            "raw_description": id_to_pair[jid][0].raw_description,
        }
        for jid in shortlist_ids
        if jid in id_to_pair
    ]

    # Stage 3: the actual agent. Bounded to `shortlist` only — never the full
    # fetched pool — so worst-case LLM calls per run stay small and predictable.
    search_fn = _make_search_fn(
        new_jobs, job_key_to_posting, already_shortlisted=set(shortlist_ids)
    )
    result = agentic_matcher.run_agent(
        profile=_profile_dict(profile), shortlist=shortlist, search_fn=search_fn
    )

    metrics.note("agentic_scored", len(result.scores))
    metrics.note("agentic_stopped_reason", result.stopped_reason)
    metrics.note("agentic_iterations", result.iterations_used)

    for job_id, score_info in result.scores.items():
        jm = match_by_job_id.get(job_id)
        if jm is None:
            continue
        explanation = f"[agentic] score={score_info['score']:.2f} — {score_info['rationale']}"
        draft = result.drafts.get(job_id)
        if draft:
            explanation += f"\n{draft}"
        jm.explanation = explanation


def _fetch_group(
    db: Session,
    targets: list,
    query: JobQuery,
    metrics: StageMetrics,
) -> tuple[list[NormalizedJob], list[FailedTarget], dict[str, dict]]:
    """Fetch + normalize + security-filter for one query group (a set of
    profiles sharing identical preferred_titles). Mirrors steps 5-9b of
    run_fetch_and_match, but is query-scoped rather than profile-scoped so it
    can be called once per unique title group instead of once per profile.

    Returns (normalized_jobs, failed_targets, target_outcomes) where
    target_outcomes maps target_id -> {"jobs_fetched": int, "error": str | None},
    to be mirrored onto every profile's own FetchRunTarget rows by the caller.
    """
    fetch_results: dict[str, tuple[list[RawJobPosting], Exception | None]] = {}
    with metrics.timed("fetch"):
        with ThreadPoolExecutor(max_workers=10) as pool:
            future_to_target = {pool.submit(_fetch_one, t, query): t for t in targets}
            for future in as_completed(future_to_target):
                target = future_to_target[future]
                try:
                    fetch_results[target.id] = (future.result(), None)
                except Exception as exc:
                    fetch_results[target.id] = ([], exc)

    all_raw: list[RawJobPosting] = []
    failed_targets: list[FailedTarget] = []
    target_outcomes: dict[str, dict] = {}

    for target in targets:
        raw_jobs, exc = fetch_results[target.id]
        st = db.get(SourceTarget, target.id)
        if exc:
            msg = str(exc)
            target_outcomes[target.id] = {"jobs_fetched": 0, "error": msg[:500]}
            if st:
                st.last_failure_at = datetime.utcnow()
            failed_targets.append(
                FailedTarget(
                    target_id=target.id,
                    connector=target.connector_name,
                    company_name=target.company_name,
                    error=msg[:200],
                )
            )
        else:
            target_outcomes[target.id] = {"jobs_fetched": len(raw_jobs), "error": None}
            all_raw.extend(raw_jobs)
            if st:
                st.last_success_at = datetime.utcnow()

    with metrics.timed("normalize"):
        normalized = normalize(all_raw)
    normalized = filter_disqualifying_jobs(normalized)
    return normalized, failed_targets, target_outcomes


def run_fetch_and_match_for_profiles(
    db: Session,
    profile_ids: list[str],
    connectors: list[str] | None = None,
    target_ids: list[str] | None = None,
    max_results_per_target: int | None = None,
) -> list[FetchJobsResponse]:
    """Fetch + match for multiple profiles in one run. Profiles sharing
    identical preferred_titles share one external fetch pass; postings are
    deduped once across the whole combined pool so no profile combination
    ever creates duplicate JobPosting rows. Each profile still gets its own
    FetchRun, its own title-filter, its own scores, and its own bounded
    agentic re-rank (see _run_agentic_stage) — matching what the pipeline
    already does per-profile in run_fetch_and_match, just batched.
    """
    profiles: list[Profile] = []
    for pid in profile_ids:
        p = db.get(Profile, pid)
        if not p:
            raise ValueError(f"Profile {pid!r} not found")
        profiles.append(p)

    targets = load_enabled_targets(db, connector_names=connectors, target_ids=target_ids)
    connector_map: dict[str, int] = {c.name: c.id for c in db.query(Connector).all()}

    groups: dict[tuple[str, ...], list[Profile]] = {}
    for p in profiles:
        key = tuple(sorted(p.preferred_titles or []))
        groups.setdefault(key, []).append(p)

    # Create one FetchRun (+ FetchRunTarget stubs) per profile up front, same
    # pattern as run_fetch_and_match, so GET /tasks/{fetch_run_id} keeps
    # working unchanged per profile.
    fetch_runs: dict[str, FetchRun] = {}
    run_target_maps: dict[str, dict[str, FetchRunTarget]] = {}
    for p in profiles:
        fr = FetchRun(
            profile_id=p.id,
            status="running",
            requested_connectors=connectors,
            requested_target_ids=target_ids,
        )
        db.add(fr)
        fetch_runs[p.id] = fr
    db.flush()
    for p in profiles:
        rt_map: dict[str, FetchRunTarget] = {}
        for target in targets:
            rt = FetchRunTarget(fetch_run_id=fetch_runs[p.id].id, source_target_id=target.id, status="running")
            db.add(rt)
            rt_map[target.id] = rt
        run_target_maps[p.id] = rt_map
    db.commit()
    for fr in fetch_runs.values():
        db.refresh(fr)
    for rt_map in run_target_maps.values():
        for rt in rt_map.values():
            db.refresh(rt)

    metrics = StageMetrics()

    all_normalized: list[NormalizedJob] = []
    group_failed: dict[tuple[str, ...], list[FailedTarget]] = {}
    group_raw_fetched: dict[tuple[str, ...], int] = {}
    group_normalized_count: dict[tuple[str, ...], int] = {}

    for key, group_profiles in groups.items():
        rep = group_profiles[0]
        query = JobQuery(
            preferred_titles=rep.preferred_titles or [],
            preferred_level=rep.preferred_level or [],
            location_hint=None,
            max_results_per_target=max_results_per_target,
        )
        normalized, failed, outcomes = _fetch_group(db, targets, query, metrics)
        group_failed[key] = failed
        group_raw_fetched[key] = sum(o["jobs_fetched"] for o in outcomes.values())
        group_normalized_count[key] = len(normalized)
        all_normalized.extend(normalized)

        now = datetime.utcnow()
        for p in group_profiles:
            rt_map = run_target_maps[p.id]
            for target in targets:
                rt = rt_map[target.id]
                outcome = outcomes[target.id]
                if outcome["error"]:
                    rt.status = "failed"
                    rt.error_message = outcome["error"]
                else:
                    rt.status = "success"
                    rt.jobs_fetched = outcome["jobs_fetched"]
                rt.finished_at = now

    metrics.stage("fetched", sum(group_raw_fetched.values()))
    metrics.stage("normalized", len(all_normalized))

    # Dedupe ONCE across every group's combined pool — a posting surfaced by
    # two groups' searches only ever gets one JobPosting row.
    with metrics.timed("dedupe"):
        new_jobs = dedupe(all_normalized, db, connector_map)
    metrics.stage("deduped_new", len(new_jobs))

    job_key_to_posting: dict[str, JobPosting] = {}
    for nj in new_jobs:
        cid = connector_map.get(nj.connector_name)
        if cid is None:
            continue
        jp = JobPosting(
            connector_id=cid,
            source_target_id=nj.source_target_id,
            external_id=nj.external_id,
            title=nj.title,
            company=nj.company,
            location=nj.location,
            url=nj.url,
            posted_at=nj.posted_at,
            raw_description=nj.raw_description,
            normalized_level=nj.normalized_level,
            employment_type=nj.employment_type,
            tags=nj.tags,
            metadata_json=nj.metadata_json,
        )
        try:
            jp.embedding = embedder.embed_text(f"{nj.title}\n{nj.raw_description or ''}")
        except Exception:
            jp.embedding = None
        db.add(jp)
        job_key_to_posting[f"{nj.source_target_id}:{nj.external_id}"] = jp

    db.flush()

    responses: list[FetchJobsResponse] = []
    connector_names = sorted({t.connector_name for t in targets})

    for p in profiles:
        key = tuple(sorted(p.preferred_titles or []))
        fetch_run = fetch_runs[p.id]

        domain_keywords = extract_domain_keywords(p.preferred_titles or [])
        if domain_keywords:
            profile_jobs = [j for j in new_jobs if passes_title_filter(j.title, domain_keywords)]
        else:
            profile_jobs = new_jobs

        with metrics.timed("score"):
            scores = score_jobs(p, profile_jobs)

        match_count = 0
        match_by_job_id: dict[str, JobMatch] = {}
        for nj, score in zip(profile_jobs, scores):
            jp = job_key_to_posting.get(f"{nj.source_target_id}:{nj.external_id}")
            if jp is None:
                continue
            jm = JobMatch(
                job_id=jp.id,
                profile_id=p.id,
                fetch_run_id=fetch_run.id,
                overall_score=score["overall"],
                title_score=score["title"],
                skills_score=score["skills"],
                level_score=score["level"],
                location_score=score["location"],
            )
            db.add(jm)
            match_by_job_id[jp.id] = jm
            match_count += 1

        with metrics.timed("agentic_match"):
            _run_agentic_stage(p, profile_jobs, scores, job_key_to_posting, match_by_job_id, metrics)

        my_failed = group_failed[key]
        fetch_run.total_jobs_fetched = group_raw_fetched[key]
        fetch_run.total_jobs_normalized = group_normalized_count[key]
        fetch_run.total_jobs_matched = match_count
        fetch_run.finished_at = datetime.utcnow()
        if not targets:
            fetch_run.status = "no_targets"
        elif len(my_failed) == len(targets):
            fetch_run.status = "failed"
        elif my_failed:
            fetch_run.status = "partial_success"
        else:
            fetch_run.status = "success"

        responses.append(
            FetchJobsResponse(
                fetch_run_id=fetch_run.id,
                profile_id=p.id,
                connectors=connector_names,
                target_count=len(targets),
                total_jobs_fetched=fetch_run.total_jobs_fetched,
                total_jobs_normalized=fetch_run.total_jobs_normalized,
                total_jobs_matched=fetch_run.total_jobs_matched,
                failed_targets=my_failed,
                status=fetch_run.status,
            )
        )

    metrics.log_summary()
    db.commit()
    return responses


def run_fetch_and_match(
    db: Session,
    profile_id: str,
    connectors: list[str] | None = None,
    target_ids: list[str] | None = None,
    max_results_per_target: int | None = None,
) -> FetchJobsResponse:
    # 1. Load profile
    profile = db.get(Profile, profile_id)
    if not profile:
        raise ValueError(f"Profile {profile_id!r} not found")

    # 2. Load targets and connector map (reads only — no write lock yet)
    targets = load_enabled_targets(db, connector_names=connectors, target_ids=target_ids)
    connector_map: dict[str, int] = {c.name: c.id for c in db.query(Connector).all()}

    # 3. Build query from profile preferences
    query = JobQuery(
        preferred_titles=profile.preferred_titles or [],
        preferred_level=profile.preferred_level or [],
        location_hint=None,
        max_results_per_target=max_results_per_target,
    )

    # 4. Create FetchRun + FetchRunTarget stubs and commit immediately so the
    #    write lock is released before the slow parallel HTTP fetches begin.
    fetch_run = FetchRun(
        profile_id=profile_id,
        status="running",
        requested_connectors=connectors,
        requested_target_ids=target_ids,
    )
    db.add(fetch_run)
    db.flush()

    run_target_map: dict[str, FetchRunTarget] = {}
    for target in targets:
        rt = FetchRunTarget(fetch_run_id=fetch_run.id, source_target_id=target.id, status="running")
        db.add(rt)
        run_target_map[target.id] = rt
    db.commit()  # release write lock before slow HTTP work
    # Re-bind ORM objects so they remain usable in this session after commit
    db.refresh(fetch_run)
    for rt in run_target_map.values():
        db.refresh(rt)

    # Pipeline stage metrics (observation only — does not change behaviour)
    metrics = StageMetrics()

    # 5. Fetch from all targets in parallel — pure HTTP, no DB access in threads
    fetch_results: dict[str, tuple[list[RawJobPosting], Exception | None]] = {}
    with metrics.timed("fetch"):
        with ThreadPoolExecutor(max_workers=10) as pool:
            future_to_target = {pool.submit(_fetch_one, t, query): t for t in targets}
            for future in as_completed(future_to_target):
                target = future_to_target[future]
                try:
                    fetch_results[target.id] = (future.result(), None)
                except Exception as exc:
                    fetch_results[target.id] = ([], exc)

    # 8. Apply results sequentially (DB writes are not thread-safe)
    all_raw: list[RawJobPosting] = []
    failed_targets: list[FailedTarget] = []

    for target in targets:
        raw_jobs, exc = fetch_results[target.id]
        rt = run_target_map[target.id]
        st = db.get(SourceTarget, target.id)

        if exc:
            msg = str(exc)
            rt.status = "failed"
            rt.error_message = msg[:500]
            rt.finished_at = datetime.utcnow()
            if st:
                st.last_failure_at = datetime.utcnow()
            failed_targets.append(
                FailedTarget(
                    target_id=target.id,
                    connector=target.connector_name,
                    company_name=target.company_name,
                    error=msg[:200],
                )
            )
        else:
            rt.status = "success"
            rt.jobs_fetched = len(raw_jobs)
            rt.finished_at = datetime.utcnow()
            all_raw.extend(raw_jobs)
            if st:
                st.last_success_at = datetime.utcnow()

    fetch_run.total_jobs_fetched = len(all_raw)
    metrics.stage("fetched", len(all_raw))

    # 9. Normalize
    with metrics.timed("normalize"):
        normalized = normalize(all_raw)
    fetch_run.total_jobs_normalized = len(normalized)
    metrics.stage("normalized", len(normalized))

    # 9b. Drop jobs requiring US security clearance or citizenship
    normalized = filter_disqualifying_jobs(normalized)
    metrics.stage("after_security", len(normalized))

    # 9c. Hard title filter — drop jobs whose title has no domain keyword from preferred_titles
    domain_keywords = extract_domain_keywords(profile.preferred_titles or [])
    if domain_keywords:
        before = len(normalized)
        normalized = [j for j in normalized if passes_title_filter(j.title, domain_keywords)]
        dropped = before - len(normalized)
        if dropped:
            import logging
            logging.getLogger(__name__).info("[title_filter] dropped %d jobs not matching keywords %s", dropped, domain_keywords)
    metrics.stage("after_title", len(normalized))

    # 10. Deduplicate against DB
    with metrics.timed("dedupe"):
        new_jobs = dedupe(normalized, db, connector_map)
    metrics.stage("deduped_new", len(new_jobs))

    # 11. Persist new job postings
    job_key_to_posting: dict[str, JobPosting] = {}
    for nj in new_jobs:
        cid = connector_map.get(nj.connector_name)
        if cid is None:
            continue
        jp = JobPosting(
            connector_id=cid,
            source_target_id=nj.source_target_id,
            external_id=nj.external_id,
            title=nj.title,
            company=nj.company,
            location=nj.location,
            url=nj.url,
            posted_at=nj.posted_at,
            raw_description=nj.raw_description,
            normalized_level=nj.normalized_level,
            employment_type=nj.employment_type,
            tags=nj.tags,
            metadata_json=nj.metadata_json,
        )
        # Stage 2 (see embedder.py): embed once at ingestion, cached on the row
        # forever after — never recomputed for future runs/profiles against
        # this same posting. Best-effort: embed_text() returns None (and this
        # stays None) if no gemini_api_key is configured or the call fails.
        try:
            jp.embedding = embedder.embed_text(f"{nj.title}\n{nj.raw_description or ''}")
        except Exception:
            jp.embedding = None
        db.add(jp)
        job_key_to_posting[f"{nj.source_target_id}:{nj.external_id}"] = jp

    db.flush()

    # 12. Score and persist job matches
    with metrics.timed("score"):
        scores = score_jobs(profile, new_jobs)
    # Score distribution — record real stats so the "strong match" cutoff is
    # data-informed rather than guessed. Strong = overall >= 0.5.
    overalls = sorted((s.get("overall", 0.0) for s in scores), reverse=True)
    if overalls:
        metrics.note("score_max", round(overalls[0], 3))
        metrics.note("score_avg", round(sum(overalls) / len(overalls), 3))
        for thr in (0.6, 0.5, 0.4, 0.3):
            metrics.note(f"matches_ge_{thr}", sum(1 for v in overalls if v >= thr))
    # strong_matches is a quality note, NOT the funnel terminal: the funnel ends at
    # deduped_new (the matches actually surfaced), so noise_cut is the honest
    # fetched->surfaced reduction rather than a score-threshold artifact.
    metrics.note("strong_matches_ge_0.5", sum(1 for s in scores if s.get("overall", 0) >= 0.5))
    match_count = 0
    match_by_job_id: dict[str, JobMatch] = {}
    for nj, score in zip(new_jobs, scores):
        jp = job_key_to_posting.get(f"{nj.source_target_id}:{nj.external_id}")
        if jp is None:
            continue
        jm = JobMatch(
            job_id=jp.id,
            profile_id=profile_id,
            fetch_run_id=fetch_run.id,
            overall_score=score["overall"],
            title_score=score["title"],
            skills_score=score["skills"],
            level_score=score["level"],
            location_score=score["location"],
        )
        db.add(jm)
        match_by_job_id[jp.id] = jm
        match_count += 1

    # 12b. Stage 2+3 — agentic re-rank + bounded LLM scoring (see
    # docs/03-agents-flows.md "Agentic matching funnel"). Best-effort: any
    # missing API key or failure just leaves the Stage 1 heuristic scores
    # already persisted above untouched.
    with metrics.timed("agentic_match"):
        _run_agentic_stage(profile, new_jobs, scores, job_key_to_posting, match_by_job_id, metrics)

    # 13. Finalise fetch run
    fetch_run.total_jobs_matched = match_count
    # funnel terminal is strong_matches (already recorded); log the whole run
    metrics.log_summary()  # prints the funnel + drop %s + timings to the logger
    fetch_run.finished_at = datetime.utcnow()
    if not targets:
        fetch_run.status = "no_targets"
    elif len(failed_targets) == len(targets):
        fetch_run.status = "failed"
    elif failed_targets:
        fetch_run.status = "partial_success"
    else:
        fetch_run.status = "success"

    db.commit()

    return FetchJobsResponse(
        fetch_run_id=fetch_run.id,
        profile_id=profile_id,
        connectors=sorted({t.connector_name for t in targets}),
        target_count=len(targets),
        total_jobs_fetched=fetch_run.total_jobs_fetched,
        total_jobs_normalized=fetch_run.total_jobs_normalized,
        total_jobs_matched=fetch_run.total_jobs_matched,
        failed_targets=failed_targets,
        status=fetch_run.status,
    )
