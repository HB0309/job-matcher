"""Fixture-based connector tests: mocks httpx at the module level and feeds
each connector a canned response shaped like the real API, then asserts the
parsed RawJobPosting fields and the fetch loop's pagination/cap/dedup
behavior. Covers the 5 REST-API connectors (remoteok, themuse, remotive,
adzuna, jobright); dice (Playwright) and linkedin (linkedin-api auth) need
heavier fixture infrastructure and are intentionally out of scope here.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.workers.connectors import adzuna, jobright, remoteok, remotive, themuse
from app.workers.connectors.base import JobQuery, SourceTargetDTO


def make_target(**kwargs):
    defaults = dict(id="t1", connector_name="x", company_name="x", base_url="https://example.com", config={})
    defaults.update(kwargs)
    return SourceTargetDTO(**defaults)


def make_query(**kwargs):
    defaults = dict(preferred_titles=["Software Engineer"], preferred_level=[], location_hint=None, max_results_per_target=200)
    defaults.update(kwargs)
    return JobQuery(**defaults)


def fake_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock() if status_code < 400 else MagicMock(side_effect=Exception(f"{status_code} error"))
    return resp


# ---------------------------------------------------------------------------
# RemoteOK
# ---------------------------------------------------------------------------


def test_remoteok_parses_valid_jobs_and_skips_metadata_row():
    # RemoteOK's real API always returns a metadata object (no "slug") as item 0.
    payload = [
        {"legal": "https://remoteok.com/legal"},
        {"id": "123", "slug": "backend-engineer-acme", "position": "Backend Engineer", "company": "Acme",
         "url": "https://remoteok.com/remote-jobs/123", "tags": ["python", "aws"], "epoch": 1700000000},
    ]
    with patch.object(remoteok.httpx, "get", return_value=fake_response(payload)):
        postings = remoteok.RemoteOKConnector().fetch_jobs(make_target(), make_query())

    assert len(postings) == 1
    p = postings[0]
    assert p.external_id == "123"
    assert p.title == "Backend Engineer"
    assert p.company == "Acme"
    assert p.location == "Remote"
    assert p.connector_name == "remoteok"


def test_remoteok_dedupes_within_batch_across_titles():
    payload = [
        {"legal": "x"},
        {"id": "1", "slug": "a", "position": "Engineer", "company": "Acme", "url": "https://x.com/1"},
    ]
    with patch.object(remoteok.httpx, "get", return_value=fake_response(payload)):
        postings = remoteok.RemoteOKConnector().fetch_jobs(
            make_target(), make_query(preferred_titles=["Software Engineer", "Backend Engineer"])
        )
    # Same job returned for both title tags -> deduped to one.
    assert len(postings) == 1


def test_remoteok_fetch_failure_returns_empty_not_raise():
    with patch.object(remoteok.httpx, "get", side_effect=RuntimeError("network down")):
        postings = remoteok.RemoteOKConnector().fetch_jobs(make_target(), make_query())
    assert postings == []


def test_remoteok_title_to_tag_strips_generic_words():
    # Only "engineer" is in RemoteOK's local _GENERIC_WORDS set (not "senior") —
    # first surviving word wins.
    assert remoteok._title_to_tag("Security Engineer") == "security"
    assert remoteok._title_to_tag("Engineer Developer") == "engineer"  # both generic -> falls back to first word


# ---------------------------------------------------------------------------
# The Muse
# ---------------------------------------------------------------------------


def test_themuse_parses_job_and_strips_html_description():
    page1 = {
        "results": [
            {
                "id": 555, "name": "Backend Engineer",
                "company": {"name": "Acme"},
                "refs": {"landing_page": "https://themuse.com/jobs/555"},
                "locations": [{"name": "Remote"}],
                "publication_date": "2026-01-01T00:00:00Z",
                "contents": "<p>Build <b>things</b>.</p>",
                "levels": [{"name": "Mid Level"}],
            }
        ],
        "total": 1,
    }
    with patch.object(themuse.httpx, "get", return_value=fake_response(page1)):
        postings = themuse.TheMuseConnector().fetch_jobs(make_target(), make_query(preferred_level=["mid"]))

    assert len(postings) == 1
    p = postings[0]
    assert p.external_id == "555"
    # Each tag becomes a literal space (not collapsed), per the connector's regex.
    assert p.raw_description == "Build  things ."
    assert p.location == "Remote"


def test_themuse_skips_jobs_missing_required_fields():
    page1 = {"results": [{"id": 1, "name": "", "company": {}, "refs": {}}], "total": 1}
    with patch.object(themuse.httpx, "get", return_value=fake_response(page1)):
        postings = themuse.TheMuseConnector().fetch_jobs(make_target(), make_query())
    assert postings == []


def test_themuse_stops_pagination_when_total_reached():
    page1 = {"results": [{"id": i, "name": "Eng", "company": {"name": "A"}, "refs": {"landing_page": f"https://x.com/{i}"}} for i in range(20)], "total": 20}
    with patch.object(themuse.httpx, "get", return_value=fake_response(page1)) as mock_get:
        themuse.TheMuseConnector().fetch_jobs(make_target(), make_query(preferred_level=[]))
    # Only one page needed since 20 results == reported total.
    assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# Remotive
# ---------------------------------------------------------------------------


def test_remotive_parses_job_and_prepends_category_tag():
    payload = {
        "jobs": [
            {
                "id": 42, "title": "Security Engineer", "company_name": "Acme",
                "url": "https://remotive.com/jobs/42",
                "candidate_required_location": "USA",
                "publication_date": "2026-01-01T00:00:00Z",
                "description": "<p>Secure things.</p>",
                "tags": ["python"], "category": "Cyber Security",
                "job_type": "full_time",
            }
        ]
    }
    with patch.object(remotive.httpx, "get", return_value=fake_response(payload)):
        postings = remotive.RemotiveConnector().fetch_jobs(make_target(), make_query(preferred_titles=["Security Engineer"]))

    assert len(postings) == 1
    p = postings[0]
    assert p.external_id == "42"
    assert "Cyber Security" in p.metadata["tags"]
    assert p.employment_type == "full_time"


def test_remotive_skips_jobs_without_url():
    payload = {"jobs": [{"id": 1, "title": "Eng", "company_name": "Acme", "url": ""}]}
    with patch.object(remotive.httpx, "get", return_value=fake_response(payload)):
        postings = remotive.RemotiveConnector().fetch_jobs(make_target(), make_query())
    assert postings == []


def test_remotive_keyword_to_category_mapping():
    assert remotive._keyword_to_category("Security Engineer") == "cybersecurity"
    assert remotive._keyword_to_category("SOC Analyst") == "cybersecurity"
    assert remotive._keyword_to_category("Product Manager") == "product"
    assert remotive._keyword_to_category("Zoologist") is None


# ---------------------------------------------------------------------------
# Adzuna
# ---------------------------------------------------------------------------


def test_adzuna_raises_clear_error_without_credentials():
    # Deliberately NOT caught inside the connector — this propagates up so the
    # orchestrator's per-target exception handling surfaces a helpful
    # "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set" message in failed_targets,
    # rather than the connector silently returning an empty list.
    with patch.object(adzuna.settings, "adzuna_app_id", ""), patch.object(adzuna.settings, "adzuna_app_key", ""):
        with pytest.raises(RuntimeError, match="ADZUNA_APP_ID"):
            adzuna.AdzunaConnector().fetch_jobs(make_target(), make_query())


def test_adzuna_parses_job_with_credentials():
    payload = {
        "results": [
            {
                "id": "999", "title": "Backend Engineer",
                "company": {"display_name": "Acme"},
                "redirect_url": "https://adzuna.com/jobs/999",
                "location": {"area": ["US", "CA", "San Francisco"]},
                "created": "2026-01-01T00:00:00Z",
                "description": "Build things",
                "contract_type": "permanent",
                "category": {"label": "IT Jobs"},
            }
        ],
        "count": 1,
    }
    with patch.object(adzuna.settings, "adzuna_app_id", "id"), patch.object(adzuna.settings, "adzuna_app_key", "key"):
        with patch.object(adzuna.httpx, "get", return_value=fake_response(payload)):
            postings = adzuna.AdzunaConnector().fetch_jobs(make_target(), make_query())

    assert len(postings) == 1
    p = postings[0]
    assert p.external_id == "999"
    assert p.location == "San Francisco, CA, US"
    assert p.metadata["tags"] == ["IT"]


# ---------------------------------------------------------------------------
# JobRight
# ---------------------------------------------------------------------------


def test_jobright_parses_job_with_assembled_description():
    item = {
        "jobResult": {
            "jobId": "abc123", "jobTitle": "Backend Engineer", "isRemote": True,
            "jobSummary": "Great role.",
            "coreResponsibilities": ["Build APIs", "Write tests"],
            "requirements": ["3+ years Python"],
            "jobSeniority": "Mid",
        },
        "companyResult": {"companyName": "Acme"},
    }
    p = jobright._parse_job(item, "target-1")
    assert p is not None
    assert p.external_id == "abc123"
    assert p.location == "Remote"
    assert "Build APIs" in p.raw_description
    assert "3+ years Python" in p.raw_description


def test_jobright_skips_item_without_job_id_or_title():
    assert jobright._parse_job({"jobResult": {"jobTitle": "Engineer"}, "companyResult": {}}, "t1") is None
    assert jobright._parse_job({"jobResult": {"jobId": "1"}, "companyResult": {}}, "t1") is None


def test_jobright_fetch_jobs_respects_page_cap(monkeypatch):
    # Every page returns the SAME job (simulates the real-world runaway
    # pagination bug: most pages return already-seen postings). Confirms
    # _MAX_PAGES_PER_TITLE bounds total requests instead of running away.
    call_count = {"n": 0}

    def fake_get_build_id():
        return "build123"

    def fake_fetch_page(build_id, query, position):
        call_count["n"] += 1
        return {
            "jobList": [{
                "jobResult": {"jobId": "same-job", "jobTitle": "Engineer"},
                "companyResult": {"companyName": "Acme"},
            }],
            "totalJobs": 100000,  # far larger than what's actually reachable
        }

    monkeypatch.setattr(jobright, "_get_build_id", fake_get_build_id)
    monkeypatch.setattr(jobright, "_fetch_page", fake_fetch_page)

    postings = jobright.JobRightConnector().fetch_jobs(make_target(), make_query(preferred_titles=["Engineer"]))

    assert len(postings) == 1  # deduped to the one unique job
    assert call_count["n"] == jobright._MAX_PAGES_PER_TITLE  # bounded, not 100000/_PAGE_SIZE pages
