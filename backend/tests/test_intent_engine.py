"""Covers every branch of intent_engine._classify (the deterministic
next-best-action rule table), plus a DB-backed smoke test of assess()/
assess_batch() to confirm the SQLAlchemy wiring around it is correct."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ApplicationDraft, JobPosting, Profile, SavedJob, User, Connector, SourceTarget
from app.workers.intent_engine import _classify, assess, assess_batch


def make_saved(status="saved"):
    s = MagicMock(spec=SavedJob)
    s.status = status
    return s


def make_draft(status="draft"):
    d = MagicMock(spec=ApplicationDraft)
    d.status = status
    return d


def test_no_saved_job_context():
    intent, reasons = _classify(None, None)
    assert intent == "prepare_draft"
    assert "no saved job context" in reasons


def test_applied_short_circuits_regardless_of_draft():
    # Even with an approved draft, an already-applied saved job is manual_only —
    # applied status wins over any draft state.
    intent, reasons = _classify(make_saved("applied"), make_draft("approved"))
    assert intent == "manual_only"
    assert "saved job marked applied" in reasons


def test_saved_no_draft_yet():
    intent, reasons = _classify(make_saved("saved"), None)
    assert intent == "prepare_draft"
    assert "no application draft exists" in reasons


def test_draft_stale():
    intent, reasons = _classify(make_saved("saved"), make_draft("stale"))
    assert intent == "refresh_draft"
    assert "draft is stale (profile changed)" in reasons


def test_draft_approved():
    intent, reasons = _classify(make_saved("saved"), make_draft("approved"))
    assert intent == "start_apply"
    assert "draft approved" in reasons


def test_draft_review_pending():
    intent, reasons = _classify(make_saved("saved"), make_draft("review_pending"))
    assert intent == "review_draft"
    assert "status is review_pending" in reasons


def test_draft_discarded_goes_back_to_prepare():
    intent, reasons = _classify(make_saved("saved"), make_draft("discarded"))
    assert intent == "prepare_draft"
    assert "previous draft discarded" in reasons


def test_draft_unexpected_status_falls_back_to_prepare():
    intent, reasons = _classify(make_saved("saved"), make_draft("draft"))
    assert intent == "prepare_draft"
    assert any("unexpected status" in r for r in reasons)


@pytest.mark.parametrize(
    "intent,expected_action_type,expected_confidence",
    [
        ("prepare_draft", "create_draft", 0.95),
        ("review_draft", "open_draft_panel", 0.95),
        ("refresh_draft", "regenerate_draft", 0.9),
        ("start_apply", "start_apply", 0.85),
        ("manual_only", "none", 0.99),
    ],
)
def test_build_response_confidence_and_action_mapping(intent, expected_action_type, expected_confidence):
    from app.workers.intent_engine import _build_response

    resp = _build_response("apply_tab", "profile-1", "saved-1", intent, ["r1"])
    assert resp.intent == intent
    assert resp.confidence == expected_confidence
    assert resp.recommended_action.type == expected_action_type


# --- DB-backed smoke test: confirms assess()/assess_batch() wire _classify
# correctly through real SavedJob/ApplicationDraft rows, not just that the
# pure function is correct in isolation. ---

def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_job(db):
    connector = Connector(name="remoteok", display_name="RemoteOK", enabled=True)
    db.add(connector)
    db.flush()
    target = SourceTarget(connector_id=connector.id, company_name="remoteok", base_url="https://example.com", enabled=True)
    db.add(target)
    db.flush()
    job = JobPosting(
        connector_id=connector.id,
        source_target_id=target.id,
        external_id="j1",
        title="Software Engineer",
        company="Acme",
        url="https://example.com/j1",
    )
    db.add(job)
    db.flush()
    return job


def test_assess_batch_end_to_end():
    db = make_db()
    user = User(email="t@example.com", password_hash="x")
    db.add(user)
    db.flush()
    profile = Profile(user_id=user.id, preferred_titles=[], preferred_level=[])
    db.add(profile)
    db.flush()
    job = seed_job(db)

    saved = SavedJob(profile_id=profile.id, job_id=job.id, status="saved")
    db.add(saved)
    db.flush()
    draft = ApplicationDraft(
        profile_id=profile.id, saved_job_id=saved.id, job_id=job.id, status="review_pending"
    )
    db.add(draft)
    db.commit()

    # assess(): single lookup, draft exists with review_pending -> review_draft
    single = assess(db, surface="apply_tab", profile_id=profile.id, saved_job_id=saved.id)
    assert single.intent == "review_draft"

    # assess(): unknown saved_job_id -> no saved job context -> prepare_draft
    missing = assess(db, surface="apply_tab", profile_id=profile.id, saved_job_id="does-not-exist")
    assert missing.intent == "prepare_draft"

    # assess_batch(): empty list short-circuits without querying
    assert assess_batch(db, surface="apply_tab", profile_id=profile.id, saved_job_ids=[]) == []

    # assess_batch(): mixes a real saved+draft row with an unknown id, order preserved
    batch = assess_batch(
        db, surface="apply_tab", profile_id=profile.id, saved_job_ids=[saved.id, "does-not-exist"]
    )
    assert [r.intent for r in batch] == ["review_draft", "prepare_draft"]
    assert [r.saved_job_id for r in batch] == [saved.id, "does-not-exist"]
