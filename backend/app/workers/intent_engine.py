"""Deterministic intent classifier for the Apply Extension Layer.

Given the current state of a saved job (and its latest application draft, if any),
return the next-best-action with reasons. No model calls — pure state rules.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ApplicationDraft, SavedJob
from app.schemas import (
    IntentAssessmentResponse,
    IntentKind,
    IntentSurface,
    RecommendedAction,
)


@dataclass
class IntentInput:
    profile_id: str
    saved_job: SavedJob | None
    draft: ApplicationDraft | None
    surface: IntentSurface = "apply_tab"


_ACTIONS: dict[IntentKind, RecommendedAction] = {
    "prepare_draft": RecommendedAction(type="create_draft", label="Generate application draft"),
    "review_draft": RecommendedAction(type="open_draft_panel", label="Review draft"),
    "refresh_draft": RecommendedAction(type="regenerate_draft", label="Regenerate draft"),
    "start_apply": RecommendedAction(type="start_apply", label="Start apply"),
    "manual_only": RecommendedAction(type="none", label="Applied"),
}

_CONFIDENCE: dict[IntentKind, float] = {
    "prepare_draft": 0.95,
    "review_draft": 0.95,
    "refresh_draft": 0.9,
    "start_apply": 0.85,
    "manual_only": 0.99,
}


def _classify(saved: SavedJob | None, draft: ApplicationDraft | None) -> tuple[IntentKind, list[str]]:
    if saved is None:
        return "prepare_draft", ["no saved job context"]

    if saved.status == "applied":
        return "manual_only", ["saved job marked applied"]

    if draft is None:
        return "prepare_draft", ["job is saved", "no application draft exists"]

    if draft.status == "stale":
        return "refresh_draft", ["draft exists", "draft is stale (profile changed)"]

    if draft.status == "approved":
        return "start_apply", ["draft exists", "draft approved"]

    if draft.status == "review_pending":
        return "review_draft", ["draft exists", "status is review_pending"]

    if draft.status == "discarded":
        return "prepare_draft", ["previous draft discarded"]

    # draft.status == "draft" or unknown — treat as needing review-pending generation
    return "prepare_draft", [f"draft has unexpected status '{draft.status}'"]


def _build_response(
    surface: IntentSurface,
    profile_id: str,
    saved_job_id: str | None,
    intent: IntentKind,
    reasons: list[str],
) -> IntentAssessmentResponse:
    return IntentAssessmentResponse(
        surface=surface,
        profile_id=profile_id,
        saved_job_id=saved_job_id,
        intent=intent,
        confidence=_CONFIDENCE[intent],
        reasons=reasons,
        recommended_action=_ACTIONS[intent],
    )


def assess(
    db: Session,
    *,
    surface: IntentSurface,
    profile_id: str,
    saved_job_id: str | None,
) -> IntentAssessmentResponse:
    saved = (
        db.query(SavedJob).filter(SavedJob.id == saved_job_id).first()
        if saved_job_id
        else None
    )
    draft = (
        db.query(ApplicationDraft)
        .filter(
            ApplicationDraft.profile_id == profile_id,
            ApplicationDraft.saved_job_id == saved_job_id,
        )
        .first()
        if saved_job_id
        else None
    )
    intent, reasons = _classify(saved, draft)
    return _build_response(surface, profile_id, saved_job_id, intent, reasons)


def assess_batch(
    db: Session,
    *,
    surface: IntentSurface,
    profile_id: str,
    saved_job_ids: list[str],
) -> list[IntentAssessmentResponse]:
    if not saved_job_ids:
        return []

    saved_rows = {
        s.id: s
        for s in db.query(SavedJob).filter(SavedJob.id.in_(saved_job_ids)).all()
    }
    drafts = (
        db.query(ApplicationDraft)
        .filter(
            ApplicationDraft.profile_id == profile_id,
            ApplicationDraft.saved_job_id.in_(saved_job_ids),
        )
        .all()
    )
    draft_by_saved = {d.saved_job_id: d for d in drafts}

    out: list[IntentAssessmentResponse] = []
    for sj_id in saved_job_ids:
        intent, reasons = _classify(saved_rows.get(sj_id), draft_by_saved.get(sj_id))
        out.append(_build_response(surface, profile_id, sj_id, intent, reasons))
    return out
