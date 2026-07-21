"""Unit tests for DeterministicProvider and helper functions.

No DB, no network calls.
"""
from unittest.mock import MagicMock

import pytest

from app.workers.application_drafter import (
    DeterministicProvider,
    _compute_facts,
    _keyword_gap,
    _confidence_from_match,
    _deterministic_qa,
    _structured_resume,
)


def _profile(skills=None, titles=None, levels=None, headline="Engineer", years=2):
    p = MagicMock()
    p.skills = skills or ["python", "sql", "docker"]
    p.preferred_titles = titles or ["Software Engineer"]
    p.preferred_level = levels or ["mid"]
    p.headline = headline
    p.years_experience = years
    return p


def _job(tags=None, company="Acme", title="Backend Engineer", location="Remote"):
    j = MagicMock()
    j.tags = tags or ["python", "kubernetes", "go"]
    j.company = company
    j.title = title
    j.location = location
    return j


def _match(overall=0.72, title=0.6, skills=0.5, level=0.9):
    m = MagicMock()
    m.overall_score = overall
    m.title_score = title
    m.skills_score = skills
    m.level_score = level
    return m


class TestKeywordGap:
    def test_intersection_and_missing(self):
        gap = _keyword_gap(["python", "sql", "docker"], ["python", "kubernetes", "go"])
        assert "python" in gap["matched"]
        assert "kubernetes" in gap["missing"]
        assert "sql" not in gap["missing"]

    def test_empty_profile_skills(self):
        gap = _keyword_gap([], ["python", "go"])
        assert gap["matched"] == []
        assert set(gap["missing"]) == {"python", "go"}

    def test_empty_job_tags(self):
        gap = _keyword_gap(["python"], [])
        assert gap["matched"] == []
        assert gap["missing"] == []

    def test_case_normalisation(self):
        gap = _keyword_gap(["Python", "SQL"], ["python", "sql"])
        assert set(gap["matched"]) == {"python", "sql"}
        assert gap["missing"] == []

    def test_none_inputs(self):
        gap = _keyword_gap(None, None)
        assert gap == {"matched": [], "missing": []}


class TestConfidenceFromMatch:
    def test_uses_match_score_when_present(self):
        gap = {"matched": ["a"], "missing": ["b"]}
        conf = _confidence_from_match(_match(overall=0.8), gap)
        assert conf == pytest.approx(0.8, abs=1e-4)

    def test_uses_gap_ratio_when_no_match(self):
        gap = {"matched": ["a", "b"], "missing": ["c"]}
        conf = _confidence_from_match(None, gap)
        assert conf == pytest.approx(2 / 3, abs=1e-3)

    def test_zero_when_no_match_and_empty_gap(self):
        gap = {"matched": [], "missing": []}
        conf = _confidence_from_match(None, gap)
        assert conf == 0.0


class TestDeterministicQA:
    def test_structure(self):
        qa = _deterministic_qa(_profile(titles=["SWE"], levels=["mid"], years=3))
        assert qa["work_authorization"] == "Authorized to work in the United States."
        assert qa["sponsorship"] == "No sponsorship required."
        assert qa["preferred_titles"] == ["SWE"]
        assert qa["years_experience"] == 3
        assert qa["why_this_role"] is None


class TestStructuredResume:
    def test_fields_present(self):
        p = _profile(skills=["python", "go"], headline="Senior Dev", years=5)
        r = _structured_resume(p)
        assert r["headline"] == "Senior Dev"
        assert r["years_experience"] == 5
        assert "python" in r["skills"]


class TestDeterministicProvider:
    def _run(self, profile=None, job=None, match=None):
        p = profile or _profile()
        j = job or _job()
        sv = MagicMock()
        from app.workers.application_drafter import _compute_facts
        facts = _compute_facts(p, j, match or _match())
        return DeterministicProvider().generate(p, sv, j, facts)

    def test_fit_summary_contains_company_and_title(self):
        result = self._run(job=_job(company="Globex", title="Platform Engineer"))
        assert "Globex" in result["fit_summary"]
        assert "Platform Engineer" in result["fit_summary"]

    def test_fit_summary_contains_score(self):
        result = self._run(match=_match(overall=0.72))
        assert "72%" in result["fit_summary"]

    def test_keyword_gap_keys_present(self):
        result = self._run()
        gap = result["keyword_gap_summary"]
        assert "matched" in gap
        assert "missing" in gap

    def test_matched_skills_correct(self):
        p = _profile(skills=["python", "sql"])
        j = _job(tags=["python", "go"])
        result = self._run(profile=p, job=j)
        assert "python" in result["keyword_gap_summary"]["matched"]
        assert "go" in result["keyword_gap_summary"]["missing"]

    def test_tailored_resume_headline(self):
        p = _profile(headline="Lead Engineer")
        result = self._run(profile=p)
        assert result["tailored_resume_json"]["headline"] == "Lead Engineer"

    def test_qa_answers_keys_exist(self):
        result = self._run()
        qa = result["qa_answers_json"]
        assert "work_authorization" in qa
        assert "why_this_role" in qa

    def test_confidence_score_is_float(self):
        result = self._run()
        assert isinstance(result["confidence_score"], float)
        assert 0.0 <= result["confidence_score"] <= 1.0

    def test_no_match_fallback_confidence(self):
        p = _profile(skills=["python", "sql"])
        j = _job(tags=["python", "kubernetes", "go"])
        sv = MagicMock()
        from app.workers.application_drafter import _compute_facts
        facts = _compute_facts(p, j, None)
        result = DeterministicProvider().generate(p, sv, j, facts)
        assert 0.0 <= result["confidence_score"] <= 1.0
