from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Connector, JobMatch, JobPosting, Profile
from app.schemas import (
    FetchJobsRequest,
    FetchJobsResponse,
    JobDetail,
    JobListItem,
    JobListResponse,
    ScoreBreakdown,
    ScoreExplanation,
)
from app.workers.orchestrator import run_fetch_and_match

router = APIRouter(tags=["jobs"], dependencies=[Depends(get_current_user)])

_LEVELS = ["new_grad", "entry", "junior", "mid", "senior", "staff", "principal"]


def _build_explanation(profile: Profile, job: JobPosting) -> ScoreExplanation:
    profile_skills = {s.lower() for s in (profile.skills or [])}
    job_tags = {t.lower() for t in (job.tags or [])}
    matched = sorted(profile_skills & job_tags)
    missing = sorted(job_tags - profile_skills)

    preferred = profile.preferred_level or []
    if isinstance(preferred, str):
        preferred = [preferred]
    job_level = job.normalized_level

    if not job_level:
        level_str = "level not listed (scored as partial)"
    elif not preferred:
        level_str = f"job is {job_level}"
    else:
        valid_pref = [p for p in preferred if p in _LEVELS]
        if not valid_pref or job_level not in _LEVELS:
            level_str = f"job is {job_level}"
        else:
            job_idx = _LEVELS.index(job_level)
            best = min(abs(job_idx - _LEVELS.index(p)) for p in valid_pref)
            if best == 0:
                level_str = "exact level match"
            elif best == 1:
                pref_idx = min((_LEVELS.index(p) for p in valid_pref), key=lambda i: abs(i - job_idx))
                direction = "above" if job_idx > pref_idx else "below"
                level_str = f"1 tier {direction} preferred"
            else:
                level_str = f"{best} tiers from preferred"

    _US_STATES = {
        "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
        "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
        "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
        "tx","ut","vt","va","wa","wv","wi","wy","dc",
    }
    import re as _re
    loc = (job.location or "").lower()
    if not loc:
        loc_str = "location not listed"
    elif "remote" in loc:
        loc_str = "remote (full score)"
    else:
        _m = _re.search(r",\s*([a-z]{2})$", loc)
        _state_match = _m and _m.group(1) in _US_STATES
        if any(kw in loc for kw in ["united states", "usa", " us,", "america"]) or _state_match:
            loc_str = "US-based"
        else:
            loc_str = "non-US location"

    return ScoreExplanation(
        matched_skills=matched,
        missing_skills=missing,
        skill_count_job=len(job_tags),
        skill_count_profile=len(profile_skills),
        level_explanation=level_str,
        location_explanation=loc_str,
    )


@router.post("/fetch-jobs", response_model=FetchJobsResponse, status_code=200)
def fetch_jobs(request: FetchJobsRequest, db: Session = Depends(get_db)) -> FetchJobsResponse:
    try:
        return run_fetch_and_match(
            db=db,
            profile_id=request.profile_id,
            connectors=request.connectors or None,
            target_ids=request.target_ids or None,
            max_results_per_target=request.max_results_per_target,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Fetch failed: {exc}") from exc


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    profile_id: str = Query(...),
    min_score: float | None = Query(default=None),
    connector: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    fetch_run_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=5000),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
) -> JobListResponse:
    q = (
        db.query(JobMatch, JobPosting, Connector)
        .join(JobPosting, JobMatch.job_id == JobPosting.id)
        .join(Connector, JobPosting.connector_id == Connector.id)
        .filter(JobMatch.profile_id == profile_id)
    )
    if min_score is not None:
        q = q.filter(JobMatch.overall_score >= min_score)
    if connector:
        q = q.filter(Connector.name == connector)
    if target_id:
        q = q.filter(JobPosting.source_target_id == target_id)
    if fetch_run_id:
        q = q.filter(JobMatch.fetch_run_id == fetch_run_id)

    rows = (
        q.order_by(
            JobMatch.overall_score.desc(),
            JobMatch.created_at.desc(),  # newer fetches before older same-score jobs
            JobPosting.posted_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return JobListResponse(
        profile_id=profile_id,
        jobs=[
            JobListItem(
                job_id=jp.id,
                connector=c.name,
                source_target_id=jp.source_target_id,
                company=jp.company,
                title=jp.title,
                location=jp.location,
                url=jp.url,
                posted_at=jp.posted_at,
                fetched_at=jm.created_at,
                fetch_run_id=jm.fetch_run_id,
                normalized_level=jp.normalized_level,
                tags=jp.tags or [],
                overall_score=jm.overall_score,
                title_score=jm.title_score,
                skills_score=jm.skills_score,
                level_score=jm.level_score,
                location_score=jm.location_score,
            )
            for jm, jp, c in rows
        ],
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(
    job_id: str,
    profile_id: str = Query(...),
    db: Session = Depends(get_db),
) -> JobDetail:
    row = (
        db.query(JobMatch, JobPosting, Connector)
        .join(JobPosting, JobMatch.job_id == JobPosting.id)
        .join(Connector, JobPosting.connector_id == Connector.id)
        .filter(JobMatch.job_id == job_id, JobMatch.profile_id == profile_id)
        .first()
    )
    if not row:
        raise HTTPException(404, f"Job {job_id!r} not found for profile {profile_id!r}")
    jm, jp, c = row
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    explanation = _build_explanation(profile, jp) if profile else None
    return JobDetail(
        job_id=jp.id,
        connector=c.name,
        source_target_id=jp.source_target_id,
        company=jp.company,
        title=jp.title,
        location=jp.location,
        url=jp.url,
        posted_at=jp.posted_at,
        raw_description=jp.raw_description,
        normalized_level=jp.normalized_level,
        tags=jp.tags or [],
        scores=ScoreBreakdown(
            overall=jm.overall_score,
            title=jm.title_score,
            skills=jm.skills_score,
            level=jm.level_score,
            location=jm.location_score,
        ),
        score_explanation=explanation,
    )
