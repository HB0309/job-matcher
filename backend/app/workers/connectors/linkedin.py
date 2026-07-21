"""
LinkedIn authenticated connector.

Uses the linkedin-api package (reverse-engineered Voyager API) with credentials
stored in LINKEDIN_EMAIL / LINKEDIN_PASSWORD env vars. Runs one search per
preferred_title, merges by job ID, fetches full details in parallel threads.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from linkedin_api import Linkedin

from app.config import settings
from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

MAX_JOBS = 500
DETAIL_WORKERS = 5
DETAIL_DELAY = 1.0   # seconds each thread sleeps after a detail fetch

_client: Linkedin | None = None


def _get_client() -> Linkedin:
    global _client
    if _client is None:
        email = settings.linkedin_email
        password = settings.linkedin_password
        if not email or not password:
            raise RuntimeError(
                "LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env"
            )
        log.info("Logging in to LinkedIn as %s", email)
        _client = Linkedin(email, password)
        log.info("LinkedIn login successful")
    return _client


class LinkedInConnector:
    name = "linkedin"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software engineer"]
        api = _get_client()

        cap = min(query.max_results_per_target or MAX_JOBS, MAX_JOBS)
        seen_ids: set[str] = set()
        all_job_ids: list[str] = []

        for title in titles:
            try:
                results = api.search_jobs(
                    keywords=title,
                    location_name="United States",
                    limit=min(cap, 200),  # linkedin-api caps per search at ~200
                )
                for r in results:
                    job_id = r.get("entityUrn", "").split(":")[-1]
                    if job_id and job_id not in seen_ids:
                        seen_ids.add(job_id)
                        all_job_ids.append(job_id)
            except Exception as exc:
                log.warning("LinkedIn search failed for %r: %s", title, exc)

        capped = all_job_ids[:cap]
        log.info("LinkedIn: %d unique job IDs across %d title(s) (cap=%d)", len(capped), len(titles), cap)

        postings: list[RawJobPosting] = []
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
            futures = {
                pool.submit(self._fetch_detail, api, job_id, target.id): job_id
                for job_id in capped
            }
            for fut in as_completed(futures):
                result = fut.result()
                if result:
                    postings.append(result)

        return postings

    def _fetch_detail(self, api: Linkedin, job_id: str, source_target_id) -> RawJobPosting | None:
        try:
            job = api.get_job(job_id)
            time.sleep(DETAIL_DELAY)
        except Exception as exc:
            log.debug("LinkedIn detail fetch failed for %s: %s", job_id, exc)
            time.sleep(DETAIL_DELAY)
            return None

        title = (
            job.get("title")
            or job.get("jobPostingTitle")
            or ""
        )
        if not title:
            return None

        # Company name
        company = (
            job.get("companyDetails", {})
            .get("com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany", {})
            .get("companyResolutionResult", {})
            .get("name", "")
        ) or job.get("companyName", "") or ""

        # Location
        location = job.get("formattedLocation") or job.get("workRemoteAllowed") and "Remote" or ""

        # Direct apply URL — available to logged-in users
        apply_url = self._extract_apply_url(job, job_id)

        # Description
        description = (
            job.get("description", {}).get("text", "")
            if isinstance(job.get("description"), dict)
            else str(job.get("description", ""))
        )

        # Employment type
        employment_type = None
        emp_list = job.get("employmentStatusResolutionResult") or []
        if isinstance(emp_list, list) and emp_list:
            employment_type = emp_list[0].get("localizedName")

        return RawJobPosting(
            connector_name="linkedin",
            source_target_id=source_target_id,
            external_id=job_id,
            title=title,
            company=company,
            url=apply_url,
            location=location,
            posted_at=None,
            raw_description=description,
            employment_type=employment_type,
            metadata={"source": "linkedin_auth"},
        )

    def _extract_apply_url(self, job: dict, job_id: str) -> str:
        """Return direct external apply URL if present, else LinkedIn job URL."""
        # Authenticated API exposes applyMethod with externalApplyLink
        apply = job.get("applyMethod", {})

        # "Apply on company website" path
        offsite = apply.get("com.linkedin.voyager.jobs.OffsiteApply", {})
        if offsite and isinstance(offsite, dict):
            link = offsite.get("companyApplyUrl", "")
            if isinstance(link, str) and link.startswith("http"):
                return link

        # Easy Apply — return LinkedIn job page as fallback
        return f"https://www.linkedin.com/jobs/view/{job_id}"
