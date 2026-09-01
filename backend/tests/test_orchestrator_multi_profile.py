"""Integration test for run_fetch_and_match_for_profiles: verifies that
profiles sharing identical preferred_titles share one fetch pass, that
postings are deduped once across the whole combined run (no duplicate
JobPosting rows across groups), and that each profile still gets its own
correctly title-filtered JobMatch set.

Uses a real in-memory SQLite DB (not mocks) since the function under test
does non-trivial ORM work (flush/commit/refresh) that's easy to get subtly
wrong with a mocked Session. The external fetch (`_fetch_one`) and the
agentic re-rank stage are monkeypatched — this test is about the
grouping/dedupe/per-profile-scoring logic, not live connectors or LLMs.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Connector, JobMatch, JobPosting, Profile, SourceTarget, User
from app.workers import orchestrator
from app.workers.connectors.base import RawJobPosting


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_target(db, connector_name="remoteok"):
    connector = Connector(name=connector_name, display_name=connector_name, enabled=True)
    db.add(connector)
    db.flush()
    target = SourceTarget(
        connector_id=connector.id,
        company_name=connector_name,
        base_url="https://example.com",
        enabled=True,
    )
    db.add(target)
    db.flush()
    return connector, target


def make_profile(db, user_id, preferred_titles):
    p = Profile(
        user_id=user_id,
        headline="Test Candidate",
        years_experience=2,
        skills=["python"],
        preferred_titles=preferred_titles,
        preferred_level=[],
    )
    db.add(p)
    db.flush()
    return p


def test_shared_group_fetches_once_and_dedupes_across_groups(monkeypatch):
    db = make_db()
    user = User(email="t@example.com", password_hash="x")
    db.add(user)
    db.flush()

    connector, target = seed_target(db)

    # A and B share an identical title set -> one group, one fetch call.
    # C has a different title set -> its own group, its own fetch call.
    profile_a = make_profile(db, user.id, ["Security Engineer"])
    profile_b = make_profile(db, user.id, ["Security Engineer"])
    profile_c = make_profile(db, user.id, ["AI Engineer"])
    db.commit()

    fetch_calls: list[tuple[str, ...]] = []

    def fake_fetch_one(t, query):
        fetch_calls.append(tuple(query.preferred_titles))
        if query.preferred_titles == ["Security Engineer"]:
            return [
                RawJobPosting(
                    connector_name="remoteok",
                    source_target_id=t.id,
                    external_id="sec-1",
                    title="Security Engineer",
                    company="Acme",
                    url="https://example.com/sec-1",
                )
            ]
        return [
            RawJobPosting(
                connector_name="remoteok",
                source_target_id=t.id,
                external_id="ai-1",
                title="AI Engineer",
                company="Acme",
                url="https://example.com/ai-1",
            )
        ]

    monkeypatch.setattr(orchestrator, "_fetch_one", fake_fetch_one)
    monkeypatch.setattr(orchestrator, "_run_agentic_stage", lambda *a, **k: None)

    responses = orchestrator.run_fetch_and_match_for_profiles(
        db=db,
        profile_ids=[profile_a.id, profile_b.id, profile_c.id],
        connectors=["remoteok"],
    )

    # One fetch call per unique title group (2 groups), not one per profile (3).
    assert len(fetch_calls) == 2
    assert set(fetch_calls) == {("Security Engineer",), ("AI Engineer",)}

    # One response per profile.
    assert len(responses) == 3
    assert {r.profile_id for r in responses} == {profile_a.id, profile_b.id, profile_c.id}

    # Dedup ran once across the whole combined pool: exactly 2 postings persisted
    # (the Security Engineer group's fetch is shared by A and B, so it must not
    # be persisted twice even though two profiles' groups reference it).
    postings = db.query(JobPosting).all()
    assert len(postings) == 2
    titles = {p.title for p in postings}
    assert titles == {"Security Engineer", "AI Engineer"}

    # Per-profile title filtering: A and B (Security Engineer group) each match
    # only the Security Engineer posting; C (AI Engineer group) matches only
    # the AI Engineer posting — even though scoring runs over the FULL combined
    # pool, not just each profile's own group's slice.
    sec_posting = next(p for p in postings if p.title == "Security Engineer")
    ai_posting = next(p for p in postings if p.title == "AI Engineer")

    matches_a = db.query(JobMatch).filter(JobMatch.profile_id == profile_a.id).all()
    matches_b = db.query(JobMatch).filter(JobMatch.profile_id == profile_b.id).all()
    matches_c = db.query(JobMatch).filter(JobMatch.profile_id == profile_c.id).all()

    assert {m.job_id for m in matches_a} == {sec_posting.id}
    assert {m.job_id for m in matches_b} == {sec_posting.id}
    assert {m.job_id for m in matches_c} == {ai_posting.id}

    # Each profile has its own FetchRun (not sharing one across the group).
    fetch_run_ids = {r.fetch_run_id for r in responses}
    assert len(fetch_run_ids) == 3
