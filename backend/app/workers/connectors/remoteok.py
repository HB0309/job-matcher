"""
RemoteOK connector.

Uses RemoteOK's official public JSON API (no auth needed).
Remote-only jobs. Filters by tags derived from preferred_titles.
"""
import logging
from datetime import datetime, timezone

import httpx

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_API_URL = "https://remoteok.com/api"
_TIMEOUT = 20
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _fetch_all(tag: str) -> list[dict]:
    url = f"{_API_URL}?tag={tag}" if tag else _API_URL
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        # First item is always a metadata object (has "legal" key), skip it
        return [j for j in data if isinstance(j, dict) and "slug" in j]
    except Exception as exc:
        log.warning("RemoteOK fetch failed (tag=%r): %s", tag, exc)
        return []


_GENERIC_WORDS = {"engineer", "developer", "analyst", "manager", "specialist", "lead", "new", "grad"}

def _title_to_tag(title: str) -> str:
    """Extract the primary keyword from a job title for RemoteOK's single-word tag API."""
    words = [w.lower() for w in title.split() if w.lower() not in _GENERIC_WORDS]
    return words[0] if words else title.lower().split()[0]


def _parse_job(job: dict, source_target_id: str) -> RawJobPosting | None:
    job_id = str(job.get("id", "") or job.get("slug", ""))
    title = (job.get("position") or "").strip()
    company = (job.get("company") or "").strip()
    url = job.get("url") or job.get("apply_url") or f"https://remoteok.com/remote-jobs/{job_id}"

    if not job_id or not title:
        return None

    posted_at = None
    epoch = job.get("epoch") or job.get("date")
    if epoch:
        try:
            posted_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except Exception:
            pass

    description = job.get("description") or None
    tags = job.get("tags") or []

    salary = job.get("salary") or None

    return RawJobPosting(
        connector_name="remoteok",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=company or "Unknown",
        url=url,
        location="Remote",
        posted_at=posted_at,
        raw_description=description,
        employment_type=None,
        metadata={"tags": tags, "salary": salary, "source": "remoteok_api"},
    )


class RemoteOKConnector:
    name = "remoteok"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software-engineer"]
        cap = min(query.max_results_per_target or 200, 300)

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for title in titles:
            tag = _title_to_tag(title)
            jobs = _fetch_all(tag)
            for job in jobs:
                posting = _parse_job(job, target.id)
                if posting and posting.external_id not in seen_ids:
                    seen_ids.add(posting.external_id)
                    postings.append(posting)
            if len(postings) >= cap:
                break

        log.info("RemoteOK: %d jobs from %d tag(s)", len(postings[:cap]), len(titles))
        return postings[:cap]
