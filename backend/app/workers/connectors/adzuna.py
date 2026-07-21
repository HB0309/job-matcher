"""
Adzuna connector.

Uses Adzuna's free public API — aggregates jobs from Indeed, Monster, and
hundreds of other boards. Requires a free API key from developer.adzuna.com.
Set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env.
"""
import logging
import time
from datetime import datetime

import httpx

from app.config import settings
from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_BASE = "https://api.adzuna.com/v1/api/jobs/us/search"
_TIMEOUT = 15
_PAGE_SIZE = 50
_MAX_JOBS = 200
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _search(query: str, location: str, page: int) -> dict:
    app_id = settings.adzuna_app_id
    app_key = settings.adzuna_app_key
    if not app_id or not app_key:
        raise RuntimeError(
            "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set in .env — "
            "register free at https://developer.adzuna.com"
        )
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": _PAGE_SIZE,
        "what": query,
        "where": location,
        "sort_by": "date",
        "content-type": "application/json",
    }
    url = f"{_BASE}/{page}"
    try:
        resp = httpx.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("Adzuna search failed (q=%r page=%d): %s", query, page, exc)
        return {}


def _parse_job(job: dict, source_target_id: str) -> RawJobPosting | None:
    job_id = str(job.get("id", ""))
    title = (job.get("title") or "").strip()
    company = (job.get("company") or {}).get("display_name", "").strip()
    url = (job.get("redirect_url") or "").strip()

    if not job_id or not title or not url:
        return None

    location_obj = job.get("location") or {}
    area = location_obj.get("area") or []
    location = ", ".join(reversed(area)) if area else location_obj.get("display_name") or None

    posted_at = None
    created = job.get("created")
    if created:
        try:
            posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:
            pass

    description = (job.get("description") or "").strip() or None

    contract_type = job.get("contract_type") or job.get("contract_time") or None

    # Extract category label as a tag (e.g. "IT Jobs", "Engineering Jobs")
    category = job.get("category") or {}
    category_label = (category.get("label") or "").replace(" Jobs", "").strip()
    tags = [category_label] if category_label else []

    return RawJobPosting(
        connector_name="adzuna",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=company or "Unknown",
        url=url,
        location=location,
        posted_at=posted_at,
        raw_description=description,
        employment_type=contract_type,
        metadata={
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "tags": tags,
            "source": "adzuna_api",
            "description_truncated": True,
        },
    )


class AdzunaConnector:
    name = "adzuna"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software engineer"]
        location = target.config.get("location", "United States")
        cap = min(query.max_results_per_target or _MAX_JOBS, _MAX_JOBS)

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for title in titles:
            page = 1
            while len(postings) < cap:
                data = _search(title, location, page)
                jobs = data.get("results") or []
                if not jobs:
                    break
                for job in jobs:
                    posting = _parse_job(job, target.id)
                    if posting and posting.external_id not in seen_ids:
                        seen_ids.add(posting.external_id)
                        postings.append(posting)
                total = data.get("count", 0)
                if page * _PAGE_SIZE >= total or len(jobs) < _PAGE_SIZE:
                    break
                page += 1
                time.sleep(0.5)

        log.info("Adzuna: %d jobs from %d title(s)", len(postings[:cap]), len(titles))
        return postings[:cap]
