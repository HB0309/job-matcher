"""Covers application_drafter.py: the pure keyword-gap/confidence helpers,
DeterministicProvider's output shape, provider selection (including the
HF-token-missing fallback), HuggingFaceProvider's JSON-parse/fallback
behavior (network mocked, never calls out), and the DB-backed
generate_draft()/mark_stale_for_profile() entry points."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    ApplicationDraft,
    Connector,
    JobMatch,
    JobPosting,
    Profile,
    SavedJob,
    SourceTarget,
    User,
)
from app.workers.application_drafter import (
    DeterministicProvider,
    HuggingFaceProvider,
    _compute_facts,
    _confidence_from_match,
    _deterministic_qa,
    _keyword_gap,
    _select_provider,
    _structured_resume,
    generate_draft,
    mark_stale_for_profile,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_keyword_gap_matched_and_missing():
    gap = _keyword_gap(["Python", "AWS", "Docker"], ["python", "kubernetes", "docker"])
    assert gap["matched"] == ["docker", "python"]
    assert gap["missing"] == ["kubernetes"]


def test_keyword_gap_handles_none_and_blank_entries():
    gap = _keyword_gap(None, ["  ", "python", None])
    assert gap["matched"] == []
    assert gap["missing"] == ["python"]


def test_confidence_from_match_uses_overall_score_when_present():
    match = MagicMock(spec=JobMatch)
    match.overall_score = 0.6789
    assert _confidence_from_match(match, {"matched": [], "missing": []}) == 0.6789


def test_confidence_from_match_falls_back_to_gap_ratio_when_no_match():
    gap = {"matched": ["python", "aws"], "missing": ["kubernetes"]}
    assert _confidence_from_match(None, gap) == round(2 / 3, 4)


def test_confidence_from_match_zero_total_gap_is_zero_not_divide_by_zero():
    assert _confidence_from_match(None, {"matched": [], "missing": []}) == 0.0


def test_deterministic_qa_structure():
    profile = make_profile(preferred_titles=["SWE"], preferred_level=["mid"], years_experience=3)
    qa = _deterministic_qa(profile)
    assert qa["work_authorization"] == "Authorized to work in the United States."
    assert qa["sponsorship"] == "No sponsorship required."
    assert qa["preferred_titles"] == ["SWE"]
    assert qa["years_experience"] == 3
    assert qa["why_this_role"] is None


def test_structured_resume_fields_present():
    profile = make_profile(skills=["python", "go"], headline="Senior Dev", years_experience=5)
    resume = _structured_resume(profile)
    assert resume["headline"] == "Senior Dev"
    assert resume["years_experience"] == 5
    assert "python" in resume["skills"]


# ---------------------------------------------------------------------------
# DeterministicProvider
# ---------------------------------------------------------------------------


def make_profile(**kwargs):
    p = MagicMock(spec=Profile)
    p.headline = "Backend Engineer"
    p.years_experience = 3
    p.skills = ["python", "aws"]
    p.preferred_titles = ["Backend Engineer"]
    p.preferred_level = ["mid"]
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def test_deterministic_provider_output_shape_and_score_formatting():
    facts = _compute_facts(
        make_profile(),
        MagicMock(spec=JobPosting, title="Backend Engineer", company="Acme", location="Remote", tags=["python", "kubernetes"]),
        MagicMock(spec=JobMatch, overall_score=0.823, title_score=1.0, skills_score=0.5, level_score=1.0),
    )
    result = DeterministicProvider().generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)

    assert "82%" in result["fit_summary"]
    assert "Acme" in result["fit_summary"]
    assert result["keyword_gap_summary"] == facts["keyword_gap_summary"]
    assert result["tailored_resume_json"] == facts["structured_resume"]
    assert result["confidence_score"] == facts["confidence_score"]


def test_deterministic_provider_handles_no_match_and_no_overlap():
    facts = _compute_facts(
        make_profile(skills=[]),
        MagicMock(spec=JobPosting, title="Backend Engineer", company="Acme", location=None, tags=["python"]),
        None,
    )
    result = DeterministicProvider().generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)
    assert "n/a" in result["fit_summary"]
    assert "limited overlap" in result["fit_summary"]


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def test_select_provider_defaults_to_deterministic():
    with patch("app.workers.application_drafter.settings") as mock_settings:
        mock_settings.drafting_provider = "deterministic"
        provider = _select_provider()
    assert isinstance(provider, DeterministicProvider)


def test_select_provider_huggingface_without_token_falls_back():
    with patch("app.workers.application_drafter.settings") as mock_settings:
        mock_settings.drafting_provider = "huggingface"
        mock_settings.hf_api_token = ""
        provider = _select_provider()
    assert isinstance(provider, DeterministicProvider)


def test_select_provider_huggingface_with_token():
    with patch("app.workers.application_drafter.settings") as mock_settings:
        mock_settings.drafting_provider = "huggingface"
        mock_settings.hf_api_token = "fake-token"
        mock_settings.hf_model = "some/model"
        mock_settings.hf_provider = "together"
        provider = _select_provider()
    assert isinstance(provider, HuggingFaceProvider)
    assert provider._token == "fake-token"


# ---------------------------------------------------------------------------
# HuggingFaceProvider — network mocked, never calls out
# ---------------------------------------------------------------------------


def _facts():
    return _compute_facts(
        make_profile(),
        MagicMock(spec=JobPosting, title="Backend Engineer", company="Acme", location="Remote", tags=["python"]),
        None,
    )


def test_huggingface_provider_uses_llm_output_on_valid_json():
    provider = HuggingFaceProvider(token="t", model="m", provider="p")
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"fit_summary": "LLM-written summary", "qa_free_text": {"why_this_role": "custom reason"}}'))]
    fake_client.chat_completion.return_value = fake_response
    provider._client = fake_client

    facts = _facts()
    result = provider.generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)

    assert result["fit_summary"] == "LLM-written summary"
    assert result["qa_answers_json"]["why_this_role"] == "custom reason"
    # Unset LLM qa fields keep the deterministic baseline's values, not blanked.
    assert result["qa_answers_json"]["sponsorship"] == "No sponsorship required."


def test_huggingface_provider_falls_back_to_deterministic_on_non_json():
    provider = HuggingFaceProvider(token="t", model="m", provider="p")
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="not json at all"))]
    fake_client.chat_completion.return_value = fake_response
    provider._client = fake_client

    facts = _facts()
    baseline = DeterministicProvider().generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)
    result = provider.generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)

    assert result["fit_summary"] == baseline["fit_summary"]
    # Two attempts made (both non-JSON) before falling back.
    assert fake_client.chat_completion.call_count == 2


def test_huggingface_provider_falls_back_on_network_exception():
    provider = HuggingFaceProvider(token="t", model="m", provider="p")
    fake_client = MagicMock()
    fake_client.chat_completion.side_effect = RuntimeError("network down")
    provider._client = fake_client

    facts = _facts()
    baseline = DeterministicProvider().generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)
    result = provider.generate(make_profile(), MagicMock(spec=SavedJob), MagicMock(spec=JobPosting), facts)

    assert result == baseline


# ---------------------------------------------------------------------------
# DB-backed: generate_draft() / mark_stale_for_profile()
# ---------------------------------------------------------------------------


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed(db):
    user = User(email="t@example.com", password_hash="x")
    db.add(user)
    db.flush()
    profile = Profile(user_id=user.id, headline="Backend Engineer", skills=["python"], preferred_titles=[], preferred_level=[])
    db.add(profile)
    db.flush()
    connector = Connector(name="remoteok", display_name="RemoteOK", enabled=True)
    db.add(connector)
    db.flush()
    target = SourceTarget(connector_id=connector.id, company_name="remoteok", base_url="https://example.com", enabled=True)
    db.add(target)
    db.flush()
    job = JobPosting(
        connector_id=connector.id, source_target_id=target.id, external_id="j1",
        title="Backend Engineer", company="Acme", url="https://example.com/j1", tags=["python"],
    )
    db.add(job)
    db.flush()
    saved = SavedJob(profile_id=profile.id, job_id=job.id, status="saved")
    db.add(saved)
    db.commit()
    return profile, job, saved


def test_generate_draft_creates_new_review_pending_draft():
    db = make_db()
    profile, job, saved = seed(db)

    with patch("app.workers.application_drafter.settings") as mock_settings:
        mock_settings.drafting_provider = "deterministic"
        draft = generate_draft(db, profile=profile, saved_job=saved, job_posting=job)

    assert draft.status == "review_pending"
    assert draft.tailored_resume_version == 1
    assert draft.fit_summary is not None
    assert db.query(ApplicationDraft).count() == 1


def test_generate_draft_regenerates_existing_and_bumps_version():
    db = make_db()
    profile, job, saved = seed(db)

    with patch("app.workers.application_drafter.settings") as mock_settings:
        mock_settings.drafting_provider = "deterministic"
        first = generate_draft(db, profile=profile, saved_job=saved, job_posting=job)
        first_id = first.id
        second = generate_draft(db, profile=profile, saved_job=saved, job_posting=job)

    assert second.id == first_id  # updated in place, not a new row
    assert second.tailored_resume_version == 2
    assert db.query(ApplicationDraft).count() == 1


def test_generate_draft_falls_back_to_deterministic_on_provider_exception():
    db = make_db()
    profile, job, saved = seed(db)

    broken_provider = MagicMock()
    broken_provider.name = "broken"
    broken_provider.generate.side_effect = RuntimeError("provider blew up")

    with patch("app.workers.application_drafter._select_provider", return_value=broken_provider):
        draft = generate_draft(db, profile=profile, saved_job=saved, job_posting=job)

    assert draft.status == "review_pending"
    assert draft.fit_summary is not None  # deterministic fallback still produced real content


def test_mark_stale_for_profile_only_flips_review_pending_and_approved():
    db = make_db()
    profile, job, saved = seed(db)

    with patch("app.workers.application_drafter.settings") as mock_settings:
        mock_settings.drafting_provider = "deterministic"
        generate_draft(db, profile=profile, saved_job=saved, job_posting=job)

    draft = db.query(ApplicationDraft).first()
    draft.status = "approved"
    db.commit()

    count = mark_stale_for_profile(db, profile.id, reason="profile_updated")
    db.refresh(draft)

    assert count == 1
    assert draft.status == "stale"
    assert draft.intent_snapshot_json["stale_reason"] == "profile_updated"


def test_mark_stale_for_profile_no_matching_drafts_returns_zero():
    db = make_db()
    profile, job, saved = seed(db)
    # No draft generated at all for this profile.
    assert mark_stale_for_profile(db, profile.id) == 0
