from unittest.mock import MagicMock

import pytest

from app.workers.matcher import (
    _level_score,
    _location_score,
    _skills_score,
    _title_score,
    score_job,
    score_jobs,
)
from app.workers.normalizer import NormalizedJob


def make_job(**kwargs) -> NormalizedJob:
    defaults = dict(
        connector_name="greenhouse",
        source_target_id="t1",
        external_id="j1",
        title="Software Engineer",
        company="Acme",
        url="https://example.com/job/1",
        location="Remote",
        normalized_level="senior",
        tags=["python", "aws"],
    )
    defaults.update(kwargs)
    return NormalizedJob(**defaults)


def make_profile(**kwargs) -> MagicMock:
    p = MagicMock()
    p.skills = ["python", "aws", "docker"]
    p.preferred_titles = ["software engineer"]
    p.preferred_level = ["senior"]
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


# ---------------------------------------------------------------------------
# _title_score
# ---------------------------------------------------------------------------

def test_title_score_exact_substring():
    assert _title_score(["software engineer"], "Senior Software Engineer") == 1.0

def test_title_score_no_match():
    score = _title_score(["software engineer"], "Accountant")
    assert score == 0.0

def test_title_score_partial_word_overlap():
    score = _title_score(["software engineer"], "Software Architect")
    assert 0.0 < score < 1.0

def test_title_score_empty_preferred():
    assert _title_score([], "Software Engineer") == 0.5

def test_title_score_best_of_multiple():
    score = _title_score(["accountant", "software engineer"], "Senior Software Engineer")
    assert score == 1.0


# ---------------------------------------------------------------------------
# _skills_score
# ---------------------------------------------------------------------------

def test_skills_score_full_overlap():
    assert _skills_score(["python", "aws"], ["python", "aws"]) == 1.0

def test_skills_score_no_overlap():
    assert _skills_score(["python"], ["java", "go"]) == 0.0

def test_skills_score_partial():
    score = _skills_score(["python", "aws", "docker"], ["python"])
    assert 0.0 < score < 1.0

def test_skills_score_empty_profile():
    assert _skills_score([], ["python"]) == 0.0

def test_skills_score_empty_job():
    assert _skills_score(["python"], []) == 0.0

def test_skills_score_capped_at_one():
    # More job tags than profile skills — still capped
    assert _skills_score(["python"], ["python", "aws", "docker"]) == 1.0


# ---------------------------------------------------------------------------
# _level_score
# ---------------------------------------------------------------------------

def test_level_score_exact():
    assert _level_score(["senior"], "senior") == 1.0

def test_level_score_adjacent():
    score = _level_score(["senior"], "mid")
    assert score == pytest.approx(0.5)

def test_level_score_two_apart():
    score = _level_score(["senior"], "junior")
    assert score == pytest.approx(0.0)

def test_level_score_no_preferred():
    assert _level_score([], "senior") == 0.5

def test_level_score_no_job_level():
    assert _level_score(["senior"], None) == 0.5

def test_level_score_best_of_multiple():
    score = _level_score(["junior", "senior"], "senior")
    assert score == 1.0

def test_level_score_floored_at_zero():
    score = _level_score(["new_grad"], "principal")
    assert score >= 0.0


# ---------------------------------------------------------------------------
# _location_score
# ---------------------------------------------------------------------------

def test_location_score_remote():
    assert _location_score("Remote") == 1.0

def test_location_score_remote_case_insensitive():
    assert _location_score("REMOTE, USA") == 1.0

def test_location_score_us():
    assert _location_score("New York, United States") == 0.8

def test_location_score_international():
    assert _location_score("London, UK") == 0.3

def test_location_score_none():
    assert _location_score(None) == 0.5


# ---------------------------------------------------------------------------
# score_job / score_jobs
# ---------------------------------------------------------------------------

def test_score_job_returns_all_keys():
    profile = make_profile()
    job = make_job()
    result = score_job(profile, job)
    assert set(result.keys()) == {"overall", "title", "skills", "level", "location"}

def test_score_job_overall_in_range():
    profile = make_profile()
    job = make_job()
    result = score_job(profile, job)
    assert 0.0 <= result["overall"] <= 1.0

def test_score_jobs_length():
    profile = make_profile()
    jobs = [make_job(external_id=str(i)) for i in range(5)]
    results = score_jobs(profile, jobs)
    assert len(results) == 5

def test_score_jobs_empty():
    profile = make_profile()
    assert score_jobs(profile, []) == []

def test_score_job_perfect_match():
    profile = make_profile(skills=["python", "aws"], preferred_titles=["software engineer"], preferred_level=["senior"])
    job = make_job(title="Software Engineer", tags=["python", "aws"], normalized_level="senior", location="Remote")
    result = score_job(profile, job)
    # title=1.0, skills=1.0 (2/2), level=1.0, location=1.0 → overall=1.0
    assert result["overall"] == pytest.approx(1.0)
