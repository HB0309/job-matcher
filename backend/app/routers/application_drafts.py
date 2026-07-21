from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import ApplicationDraft, JobPosting, Profile, SavedJob
from app.schemas import (
    ApplicationDraftCreate,
    ApplicationDraftPatch,
    ApplicationDraftResponse,
    KeywordGap,
)
from app.workers.application_drafter import generate_draft

router = APIRouter(tags=["application-drafts"], dependencies=[Depends(get_current_user)])


def _to_response(draft: ApplicationDraft) -> ApplicationDraftResponse:
    gap = draft.keyword_gap_summary or {}
    return ApplicationDraftResponse(
        id=draft.id,
        profile_id=draft.profile_id,
        saved_job_id=draft.saved_job_id,
        job_id=draft.job_id,
        status=draft.status,
        fit_summary=draft.fit_summary,
        keyword_gap_summary=KeywordGap(
            matched=gap.get("matched", []),
            missing=gap.get("missing", []),
        ),
        tailored_resume_json=draft.tailored_resume_json,
        tailored_resume_version=draft.tailored_resume_version,
        qa_answers_json=draft.qa_answers_json,
        intent_snapshot_json=draft.intent_snapshot_json,
        confidence_score=draft.confidence_score,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        approved_at=draft.approved_at,
    )


@router.post("/application-drafts", response_model=ApplicationDraftResponse)
def create_or_fetch_draft(body: ApplicationDraftCreate, db: Session = Depends(get_db)):
    profile = db.get(Profile, body.profile_id)
    if not profile:
        raise HTTPException(404, f"Profile {body.profile_id!r} not found")

    saved = db.get(SavedJob, body.saved_job_id)
    if not saved:
        raise HTTPException(404, f"Saved job {body.saved_job_id!r} not found")
    if saved.profile_id != body.profile_id:
        raise HTTPException(400, "Saved job does not belong to the given profile")

    job_posting = db.get(JobPosting, saved.job_id)
    if not job_posting:
        raise HTTPException(404, f"Job posting {saved.job_id!r} not found")

    existing = (
        db.query(ApplicationDraft)
        .filter(
            ApplicationDraft.profile_id == body.profile_id,
            ApplicationDraft.saved_job_id == body.saved_job_id,
        )
        .first()
    )

    # Idempotent: only regenerate if there's no draft, or it's stale, or it was discarded.
    if existing is not None and existing.status not in ("stale", "discarded"):
        return _to_response(existing)

    draft = generate_draft(db, profile=profile, saved_job=saved, job_posting=job_posting)
    return _to_response(draft)


@router.get("/application-drafts/{draft_id}", response_model=ApplicationDraftResponse)
def get_draft(draft_id: str, db: Session = Depends(get_db)):
    draft = db.get(ApplicationDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Application draft {draft_id!r} not found")
    return _to_response(draft)


@router.get("/application-drafts", response_model=ApplicationDraftResponse)
def lookup_draft(
    profile_id: str = Query(...),
    saved_job_id: str = Query(...),
    db: Session = Depends(get_db),
):
    draft = (
        db.query(ApplicationDraft)
        .filter(
            ApplicationDraft.profile_id == profile_id,
            ApplicationDraft.saved_job_id == saved_job_id,
        )
        .first()
    )
    if not draft:
        raise HTTPException(404, "No draft for this (profile, saved_job)")
    return _to_response(draft)


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review_pending", "discarded", "stale"},
    "review_pending": {"approved", "discarded", "stale"},
    "approved": {"review_pending", "stale", "discarded"},
    "stale": {"review_pending", "discarded"},
    "discarded": {"review_pending"},
}


@router.patch("/application-drafts/{draft_id}", response_model=ApplicationDraftResponse)
def patch_draft(draft_id: str, body: ApplicationDraftPatch, db: Session = Depends(get_db)):
    draft = db.get(ApplicationDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Application draft {draft_id!r} not found")

    if body.status is not None and body.status != draft.status:
        allowed = _ALLOWED_TRANSITIONS.get(draft.status, set())
        if body.status not in allowed:
            raise HTTPException(
                400,
                f"Invalid status transition: {draft.status} -> {body.status}",
            )
        draft.status = body.status
        if body.status == "approved":
            draft.approved_at = datetime.now(timezone.utc)
        elif body.status == "review_pending":
            draft.approved_at = None

    if body.qa_answers_json is not None:
        draft.qa_answers_json = body.qa_answers_json
    if body.tailored_resume_json is not None:
        draft.tailored_resume_json = body.tailored_resume_json
        draft.tailored_resume_version = (draft.tailored_resume_version or 0) + 1
    if body.fit_summary is not None:
        draft.fit_summary = body.fit_summary

    db.commit()
    db.refresh(draft)
    return _to_response(draft)


@router.post("/application-drafts/{draft_id}/apply")
def auto_apply(draft_id: str, db: Session = Depends(get_db)):
    draft = db.get(ApplicationDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Application draft {draft_id!r} not found")
    if draft.status != "approved":
        raise HTTPException(400, "Approve the draft before auto-applying")
    from app.workers.auto_apply import trigger_apply
    trigger_apply(draft_id)
    return {"status": "browser_launched"}
