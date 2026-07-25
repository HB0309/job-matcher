from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Connector, FetchRun, FetchRunTarget, JobMatch, JobPosting, Profile, SourceTarget
from app.schemas import FailedTarget, FetchJobsResponse
from app.workers.connectors.base import JobQuery, RawJobPosting
from app.workers.deduper import dedupe
from app.workers.matcher import extract_domain_keywords, passes_title_filter, score_jobs
from app.workers.normalizer import normalize
from app.workers.security_filter import filter_disqualifying_jobs
from app.workers.registry import get_connector
from app.workers.run_metrics import StageMetrics
from app.workers.target_loader import load_enabled_targets


def _fetch_one(target, query: JobQuery) -> list[RawJobPosting]:
    connector = get_connector(target.connector_name)
    return connector.fetch_jobs(target, query)


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
    for nj, score in zip(new_jobs, scores):
        jp = job_key_to_posting.get(f"{nj.source_target_id}:{nj.external_id}")
        if jp is None:
            continue
        db.add(
            JobMatch(
                job_id=jp.id,
                profile_id=profile_id,
                fetch_run_id=fetch_run.id,
                overall_score=score["overall"],
                title_score=score["title"],
                skills_score=score["skills"],
                level_score=score["level"],
                location_score=score["location"],
            )
        )
        match_count += 1

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
