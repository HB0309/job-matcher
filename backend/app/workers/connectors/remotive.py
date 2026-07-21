"""
Remotive connector.

Uses Remotive's free public API (no auth needed).
Remote-only tech jobs. Searches by keyword derived from preferred_titles.
Full job descriptions included in API response.
"""
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_API_URL = "https://remotive.com/api/remote-jobs"
_TIMEOUT = 15
_MAX_JOBS = 200
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

_CATEGORY_MAP: dict[str, str] = {
    "security": "cybersecurity",
    "cyber": "cybersecurity",
    "soc": "cybersecurity",
    "software": "software-dev",
    "frontend": "software-dev",
    "backend": "software-dev",
    "fullstack": "software-dev",
    "devops": "devops-sysadmin",
    "cloud": "devops-sysadmin",
    "data": "data",
    "ml": "data",
    "ai": "data",
    "design": "design",
    "product": "product",
    "marketing": "marketing",
}


def _keyword_to_category(keyword: str) -> str | None:
    kw = keyword.lower()
    for k, cat in _CATEGORY_MAP.items():
        if k in kw:
            return cat
    return None


def _fetch(search: str, limit: int) -> list[dict]:
    try:
        resp = httpx.get(
            _API_URL,
            params={"search": search, "limit": limit},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("jobs", [])
    except Exception as exc:
        log.warning("Remotive fetch failed (search=%r): %s", search, exc)
        return []


def _parse_job(job: dict, source_target_id: str) -> RawJobPosting | None:
    job_id = str(job.get("id", ""))
    title = (job.get("title") or "").strip()
    company = (job.get("company_name") or "").strip()
    url = (job.get("url") or "").strip()

    if not job_id or not title or not url:
        return None

    location = job.get("candidate_required_location") or "Remote"

    posted_at = None
    pub = job.get("publication_date")
    if pub:
        try:
            posted_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            pass

    # Strip HTML tags from description
    raw_desc = job.get("description") or ""
    description = re.sub(r"<[^>]+>", " ", raw_desc).strip() or None

    tags = job.get("tags") or []
    category = job.get("category") or ""
    if category and category not in tags:
        tags = [category] + tags

    job_type = job.get("job_type") or None

    return RawJobPosting(
        connector_name="remotive",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=company or "Unknown",
        url=url,
        location=location,
        posted_at=posted_at,
        raw_description=description,
        employment_type=job_type,
        metadata={"tags": tags, "salary": job.get("salary"), "source": "remotive_api"},
    )


class RemotiveConnector:
    name = "remotive"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software engineer"]
        cap = min(query.max_results_per_target or _MAX_JOBS, _MAX_JOBS)

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for title in titles:
            jobs = _fetch(title, min(cap, 100))
            for job in jobs:
                posting = _parse_job(job, target.id)
                if posting and posting.external_id not in seen_ids:
                    seen_ids.add(posting.external_id)
                    postings.append(posting)
            if len(postings) >= cap:
                break
            time.sleep(0.5)

        log.info("Remotive: %d jobs from %d title(s)", len(postings[:cap]), len(titles))
        return postings[:cap]
