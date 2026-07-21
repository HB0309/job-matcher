"""
Hiring Café connector.

Reads from hiring.cafe's public Next.js SSR pages — no auth required.
Uses /jobs/locations/united-states?query=...&page=N for search + pagination.
Each page is ~1.5 MB of server-rendered HTML containing __NEXT_DATA__.
"""
import logging
import re
import time

import httpx

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_BASE = "https://hiring.cafe"
_SEARCH_PATH = "/jobs/locations/united-states"
_TIMEOUT = 20
_PAGE_SIZE = 40   # hiring.cafe ssrPageSize
_MAX_JOBS = 120   # each page is 1.5 MB — keep total reasonable
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

_SENIORITY_MAP: dict[str, str] = {
    "intern": "new_grad",
    "entry level": "entry",
    "mid level": "mid",
    "senior level": "senior",
    "lead": "senior",
    "manager": "staff",
    "director": "principal",
    "principal": "principal",
    "staff": "staff",
    "associate": "entry",
}


def _fetch_page(query: str, page: int) -> dict:
    """Fetch one page of hiring.cafe search results and parse __NEXT_DATA__."""
    params: dict = {"page": page}
    if query:
        params["query"] = query

    resp = httpx.get(
        f"{_BASE}{_SEARCH_PATH}",
        params=params,
        headers=_HEADERS,
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ in hiring.cafe response")

    import json
    return json.loads(match.group(1)).get("props", {}).get("pageProps", {})


def _map_seniority(raw: str | None) -> str | None:
    if not raw:
        return None
    return _SENIORITY_MAP.get(raw.lower().strip())


def _parse_job(hit: dict, source_target_id: str) -> RawJobPosting | None:
    job_id = hit.get("objectID") or hit.get("id") or ""
    ji = hit.get("job_information") or {}
    v5 = hit.get("v5_processed_job_data") or {}
    ec = hit.get("enriched_company_data") or {}

    title = v5.get("core_job_title") or ji.get("title") or ""
    title = title.strip()
    if not job_id or not title:
        return None

    company = ec.get("name") or v5.get("company_name") or "Unknown"
    apply_url = hit.get("apply_url") or ""
    if not apply_url:
        return None

    location = v5.get("formatted_workplace_location") or None
    workplace = v5.get("workplace_type") or ""
    if "remote" in workplace.lower():
        location = location or "Remote"

    description_html = ji.get("description") or ""
    description = re.sub(r"<[^>]+>", " ", description_html).strip() or None

    import re as _re
    posted_at = None
    millis = v5.get("estimated_publish_date_millis")
    if millis:
        try:
            from datetime import datetime, timezone
            posted_at = datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc)
        except Exception:
            pass

    level = _map_seniority(v5.get("seniority_level"))

    commitment = v5.get("commitment") or []
    employment = commitment[0] if isinstance(commitment, list) and commitment else None

    tags = list(v5.get("technical_tools") or [])

    return RawJobPosting(
        connector_name="hiringcafe",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=company,
        url=apply_url,
        location=location,
        posted_at=posted_at,
        raw_description=description,
        employment_type=employment,
        metadata={
            "normalized_level": level,
            "tags": tags,
            "salary_min": v5.get("yearly_min_compensation"),
            "salary_max": v5.get("yearly_max_compensation"),
            "source": "hiringcafe_api",
        },
    )


class HiringCafeConnector:
    name = "hiringcafe"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software engineer"]
        cap = min(query.max_results_per_target or _MAX_JOBS, _MAX_JOBS)

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for title in titles:
            page = 1
            while len(postings) < cap:
                try:
                    page_data = _fetch_page(title, page)
                except Exception as exc:
                    log.warning("HiringCafe fetch failed (q=%r page=%d): %s", title, page, exc)
                    break

                hits = page_data.get("ssrHits") or []
                if not hits:
                    break

                for hit in hits:
                    posting = _parse_job(hit, target.id)
                    if posting and posting.external_id not in seen_ids:
                        seen_ids.add(posting.external_id)
                        postings.append(posting)

                if page_data.get("ssrIsLastPage"):
                    break
                page += 1
                time.sleep(1.0)  # pages are ~1.5 MB — be polite

        log.info("HiringCafe: %d jobs from %d title(s)", len(postings[:cap]), len(titles))
        return postings[:cap]
