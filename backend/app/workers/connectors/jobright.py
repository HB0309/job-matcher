"""
JobRight connector.

Reads from JobRight's public Next.js data API — no auth required.
Extracts buildId from the homepage, then paginates via position offset.
"""
import logging
import re
import time
from datetime import datetime

import httpx

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_BASE = "https://jobright.ai"
_TIMEOUT = 15
_PAGE_SIZE = 20
_MAX_JOBS = 200
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
}

_SENIORITY_MAP: dict[str, str] = {
    "new grad": "new_grad",
    "internship": "new_grad",
    "entry": "entry",
    "associate": "entry",
    "mid": "mid",
    "mid level": "mid",
    "senior": "senior",
    "lead": "senior",
    "manager": "staff",
    "director": "principal",
    "principal": "principal",
}

_build_id: str | None = None


def _get_build_id() -> str:
    global _build_id
    if _build_id:
        return _build_id
    resp = httpx.get(_BASE, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not extract JobRight buildId from homepage")
    _build_id = match.group(1)
    log.debug("JobRight buildId: %s", _build_id)
    return _build_id


def _fetch_page(build_id: str, query: str, position: int) -> dict:
    url = f"{_BASE}/_next/data/{build_id}/jobs/index.json"
    params = {"q": query, "position": position}
    resp = httpx.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
    if resp.status_code == 404:
        # buildId rotated — invalidate cache
        global _build_id
        _build_id = None
        raise ValueError("JobRight buildId expired — will retry")
    resp.raise_for_status()
    return resp.json().get("pageProps", {})


def _map_seniority(raw: str | None) -> str | None:
    if not raw:
        return None
    for part in re.split(r"[,/]", raw.lower()):
        mapped = _SENIORITY_MAP.get(part.strip())
        if mapped:
            return mapped
    return None


def _parse_job(item: dict, source_target_id: str) -> RawJobPosting | None:
    jr = item.get("jobResult") or {}
    cr = item.get("companyResult") or {}

    job_id = jr.get("jobId") or ""
    title = (jr.get("jobTitle") or "").strip()
    if not job_id or not title:
        return None

    company = (cr.get("companyName") or "").strip() or "Unknown"
    location = jr.get("jobLocation") or (cr.get("companyLocation") or None)
    if jr.get("isRemote"):
        location = location or "Remote"

    url = jr.get("applyLink") or jr.get("url") or f"{_BASE}/jobs/info/{job_id}"

    posted_at = None
    pub = jr.get("publishTime")
    if pub:
        try:
            posted_at = datetime.fromisoformat(pub)
        except Exception:
            pass

    parts: list[str] = []
    if jr.get("jobSummary"):
        parts.append(jr["jobSummary"])
    responsibilities = jr.get("coreResponsibilities") or []
    if isinstance(responsibilities, list) and responsibilities:
        parts.append("Responsibilities:\n" + "\n".join(f"• {r}" for r in responsibilities))
    elif isinstance(responsibilities, str) and responsibilities:
        parts.append(responsibilities)
    requirements = jr.get("requirements") or []
    if isinstance(requirements, list) and requirements:
        parts.append("Requirements:\n" + "\n".join(f"• {r}" for r in requirements))
    elif isinstance(requirements, str) and requirements:
        parts.append(requirements)
    description = "\n\n".join(parts) or None
    employment = jr.get("employmentType") or None
    level = _map_seniority(jr.get("jobSeniority"))

    tags: list[str] = jr.get("jobTags") or jr.get("recommendationTags") or []

    return RawJobPosting(
        connector_name="jobright",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=company,
        url=url,
        location=location,
        posted_at=posted_at,
        raw_description=description,
        employment_type=employment,
        metadata={
            "normalized_level": level,
            "tags": tags,
            "salary": jr.get("salaryDesc"),
            "source": "jobright_api",
        },
    )


class JobRightConnector:
    name = "jobright"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software engineer"]
        cap = min(query.max_results_per_target or _MAX_JOBS, _MAX_JOBS)

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for title in titles:
            position = 0
            retried = False
            while len(postings) < cap:
                try:
                    build_id = _get_build_id()
                    page_data = _fetch_page(build_id, title, position)
                except ValueError:
                    # buildId expired — retry once
                    if retried:
                        log.warning("JobRight buildId retry failed for %r", title)
                        break
                    retried = True
                    continue
                except Exception as exc:
                    log.warning("JobRight fetch failed (q=%r pos=%d): %s", title, position, exc)
                    break

                jobs = page_data.get("jobList") or []
                if not jobs:
                    break

                for item in jobs:
                    posting = _parse_job(item, target.id)
                    if posting and posting.external_id not in seen_ids:
                        seen_ids.add(posting.external_id)
                        postings.append(posting)

                total = page_data.get("totalJobs") or 0
                position += _PAGE_SIZE
                if position >= total:
                    break
                time.sleep(0.5)

        log.info("JobRight: %d jobs from %d title(s)", len(postings[:cap]), len(titles))
        return postings[:cap]
