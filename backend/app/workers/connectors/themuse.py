"""
The Muse connector.

Uses The Muse's free public API (no auth needed).
Filters by Software Engineering category and maps preferred_level to Muse levels.
No keyword search available — rely on the matcher to score relevance.
"""
import logging
import time
from datetime import datetime, timezone

import httpx

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_BASE = "https://www.themuse.com/api/public/jobs"
_TIMEOUT = 15
_PAGE_SIZE = 20   # Muse API fixed page size
_MAX_JOBS = 200

# Map our level names → Muse level filter values
_LEVEL_MAP: dict[str, str] = {
    "new_grad":  "Entry Level",
    "entry":     "Entry Level",
    "junior":    "Entry Level",
    "mid":       "Mid Level",
    "senior":    "Senior Level",
    "staff":     "Senior Level",
    "principal": "Senior Level",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _fetch_page(level: str | None, page: int) -> dict:
    params: dict = {"category": "Software Engineering", "page": page}
    if level:
        params["level"] = level
    try:
        resp = httpx.get(_BASE, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("Muse fetch failed (level=%r page=%d): %s", level, page, exc)
        return {}


def _parse_job(job: dict, source_target_id: str) -> RawJobPosting | None:
    job_id = str(job.get("id", ""))
    title = (job.get("name") or "").strip()
    company = (job.get("company") or {}).get("name", "").strip()
    url = (job.get("refs") or {}).get("landing_page", "")

    if not job_id or not title or not url:
        return None

    locations = job.get("locations") or []
    location = locations[0].get("name") if locations else "United States"

    posted_at = None
    pub = job.get("publication_date")
    if pub:
        try:
            posted_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            pass

    # Strip HTML from contents
    import re
    raw = job.get("contents") or ""
    description = re.sub(r"<[^>]+>", " ", raw).strip() or None

    levels = job.get("levels") or []
    level_str = levels[0].get("name") if levels else None

    return RawJobPosting(
        connector_name="themuse",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=company or "Unknown",
        url=url,
        location=location,
        posted_at=posted_at,
        raw_description=description,
        employment_type=None,
        metadata={"muse_level": level_str, "source": "themuse_api"},
    )


class TheMuseConnector:
    name = "themuse"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        cap = min(query.max_results_per_target or _MAX_JOBS, _MAX_JOBS)
        preferred = query.preferred_level or []

        # Derive unique Muse level strings from user's preferred levels
        muse_levels: list[str | None] = []
        seen_levels: set[str] = set()
        for lvl in preferred:
            mapped = _LEVEL_MAP.get(lvl)
            if mapped and mapped not in seen_levels:
                seen_levels.add(mapped)
                muse_levels.append(mapped)
        if not muse_levels:
            muse_levels = [None]  # fetch all levels

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for level in muse_levels:
            page = 0
            while len(postings) < cap:
                data = _fetch_page(level, page)
                results = data.get("results") or []
                if not results:
                    break
                for job in results:
                    posting = _parse_job(job, target.id)
                    if posting and posting.external_id not in seen_ids:
                        seen_ids.add(posting.external_id)
                        postings.append(posting)
                total = data.get("total", 0)
                if (page + 1) * _PAGE_SIZE >= total:
                    break
                page += 1
                time.sleep(0.3)

        log.info("TheMuse: %d jobs (levels=%r)", len(postings[:cap]), muse_levels)
        return postings[:cap]
