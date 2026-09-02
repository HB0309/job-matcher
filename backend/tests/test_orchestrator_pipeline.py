"""End-to-end integration test for the single-profile fetch pipeline
(orchestrator.run_fetch_and_match): fetch -> normalize -> security filter ->
title filter -> dedupe -> persist -> score -> FetchRun finalization, using a
real in-memory SQLite DB (not mocks) so the ORM writes are actually
exercised. Only the external network call (_fetch_one) and the agentic
re-rank (_run_agentic_stage, which needs real LLM keys) are stubbed —
everything else in the pipeline runs for real.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Connector, FetchRun, FetchRunTarget, JobMatch, JobPosting, Profile, SourceTarget, User
from app.workers import orchestrator
from app.workers.connectors.base import RawJobPosting


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_user_and_profile(db, preferred_titles=None, preferred_level=None, skills=None):
    user = User(email="t@example.com", password_hash="x")
    db.add(user)
    db.flush()
    profile = Profile(
        user_id=user.id,
        headline="Test Candidate",
        skills=skills or ["python", "aws"],
        preferred_titles=preferred_titles if preferred_titles is not None else ["Security Engineer"],
        preferred_level=preferred_level or [],
    )
    db.add(profile)
    db.flush()
    return profile


def seed_targets(db, names=("remoteok",)):
    targets = []
    for name in names:
        connector = Connector(name=name, display_name=name, enabled=True)
        db.add(connector)
        db.flush()
        target = SourceTarget(connector_id=connector.id, company_name=name, base_url="https://example.com", enabled=True)
        db.add(target)
        db.flush()
        targets.append((connector, target))
    return targets


def posting(external_id, title, connector_name="remoteok", source_target_id="t1", description=None):
    return RawJobPosting(
        connector_name=connector_name,
        source_target_id=source_target_id,
        external_id=external_id,
        title=title,
        company="Acme",
        url=f"https://example.com/{external_id}",
        raw_description=description,
    )


def test_full_pipeline_happy_path(monkeypatch):
    db = make_db()
    profile = seed_user_and_profile(db, preferred_titles=["Security Engineer"])
    (connector, target), = seed_targets(db)

    raw = [
        posting("1", "Security Engineer", source_target_id=target.id),
        posting("2", "Marketing Manager", source_target_id=target.id),  # dropped by title filter
        posting("3", "Security Engineer", source_target_id=target.id, description="requires active TS/SCI clearance"),  # dropped by security filter
    ]
    monkeypatch.setattr(orchestrator, "_fetch_one", lambda t, q: raw)
    monkeypatch.setattr(orchestrator, "_run_agentic_stage", lambda *a, **k: None)

    resp = orchestrator.run_fetch_and_match(db=db, profile_id=profile.id, connectors=["remoteok"])

    assert resp.status == "success"
    assert resp.total_jobs_fetched == 3
    assert resp.total_jobs_normalized == 3
    assert resp.total_jobs_matched == 1  # only posting "1" survives both filters
    assert resp.failed_targets == []

    postings = db.query(JobPosting).all()
    assert len(postings) == 1
    assert postings[0].external_id == "1"

    matches = db.query(JobMatch).filter(JobMatch.profile_id == profile.id).all()
    assert len(matches) == 1
    assert matches[0].job_id == postings[0].id

    fetch_run = db.query(FetchRun).filter(FetchRun.id == resp.fetch_run_id).first()
    assert fetch_run.status == "success"
    assert fetch_run.finished_at is not None

    run_targets = db.query(FetchRunTarget).filter(FetchRunTarget.fetch_run_id == fetch_run.id).all()
    assert len(run_targets) == 1
    assert run_targets[0].status == "success"
    assert run_targets[0].jobs_fetched == 3


def test_pipeline_dedupes_against_existing_db_rows_on_refetch(monkeypatch):
    db = make_db()
    profile = seed_user_and_profile(db, preferred_titles=["Security Engineer"])
    (connector, target), = seed_targets(db)

    raw = [posting("1", "Security Engineer", source_target_id=target.id)]
    monkeypatch.setattr(orchestrator, "_fetch_one", lambda t, q: raw)
    monkeypatch.setattr(orchestrator, "_run_agentic_stage", lambda *a, **k: None)

    first = orchestrator.run_fetch_and_match(db=db, profile_id=profile.id, connectors=["remoteok"])
    assert first.total_jobs_matched == 1
    assert db.query(JobPosting).count() == 1

    # Re-fetch: same external posting comes back again -> deduped, 0 new matches,
    # and critically no duplicate JobPosting row.
    second = orchestrator.run_fetch_and_match(db=db, profile_id=profile.id, connectors=["remoteok"])
    assert second.total_jobs_matched == 0
    assert db.query(JobPosting).count() == 1


def test_pipeline_partial_success_when_one_target_fails(monkeypatch):
    db = make_db()
    profile = seed_user_and_profile(db, preferred_titles=["Security Engineer"])
    targets = seed_targets(db, names=("remoteok", "themuse"))

    def fake_fetch_one(t, q):
        if t.connector_name == "themuse":
            raise RuntimeError("themuse is down")
        return [posting("1", "Security Engineer", connector_name="remoteok", source_target_id=t.id)]

    monkeypatch.setattr(orchestrator, "_fetch_one", fake_fetch_one)
    monkeypatch.setattr(orchestrator, "_run_agentic_stage", lambda *a, **k: None)

    resp = orchestrator.run_fetch_and_match(db=db, profile_id=profile.id, connectors=["remoteok", "themuse"])

    assert resp.status == "partial_success"
    assert len(resp.failed_targets) == 1
    assert resp.failed_targets[0].connector == "themuse"
    assert resp.failed_targets[0].error == "themuse is down"
    assert resp.total_jobs_matched == 1  # remoteok's posting still made it through


def test_pipeline_failed_status_when_all_targets_fail(monkeypatch):
    db = make_db()
    profile = seed_user_and_profile(db, preferred_titles=["Security Engineer"])
    seed_targets(db, names=("remoteok",))

    monkeypatch.setattr(orchestrator, "_fetch_one", lambda t, q: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(orchestrator, "_run_agentic_stage", lambda *a, **k: None)

    resp = orchestrator.run_fetch_and_match(db=db, profile_id=profile.id, connectors=["remoteok"])

    assert resp.status == "failed"
    assert resp.total_jobs_matched == 0
    assert len(resp.failed_targets) == 1


def test_pipeline_no_targets_status(monkeypatch):
    db = make_db()
    profile = seed_user_and_profile(db)
    # No SourceTarget rows seeded at all -> load_enabled_targets returns [].
    monkeypatch.setattr(orchestrator, "_run_agentic_stage", lambda *a, **k: None)

    resp = orchestrator.run_fetch_and_match(db=db, profile_id=profile.id, connectors=["remoteok"])

    assert resp.status == "no_targets"
    assert resp.target_count == 0
    assert resp.total_jobs_matched == 0


def test_pipeline_unknown_profile_raises_value_error(monkeypatch):
    db = make_db()
    try:
        orchestrator.run_fetch_and_match(db=db, profile_id="does-not-exist")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "does-not-exist" in str(exc)
