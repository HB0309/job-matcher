"""
Indeed RSS connector.

Uses Indeed's public RSS feed (no auth needed).
Runs one feed fetch per preferred_title, deduplicates by job URL.
"""
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

import httpx

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_BASE = "https://www.indeed.com/rss"
_TIMEOUT = 15
_MAX_PER_QUERY = 50   # RSS returns max 25; we do 2 pages
_PAGE_SIZE = 25
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


def _fetch_rss(query: str, location: str, start: int) -> list[ET.Element]:
    params = {"q": query, "l": location, "sort": "date", "limit": _PAGE_SIZE, "start": start}
    url = f"{_BASE}?{urlencode(params)}"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        return root.findall(".//item")
    except Exception as exc:
        log.warning("Indeed RSS fetch failed (q=%r start=%d): %s", query, start, exc)
        return []


def _parse_item(item: ET.Element, source_target_id: str) -> RawJobPosting | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    company = (item.findtext("source") or "").strip()

    if not title or not link:
        return None

    # Use the link URL as external_id (strip query params for dedup key)
    external_id = re.sub(r"\?.*", "", link).rstrip("/").split("/")[-1] or link[:200]

    location_raw = item.findtext("location") or ""
    if not location_raw:
        # Try to extract from description
        desc = item.findtext("description") or ""
        loc_match = re.search(r"<b>Location</b>:\s*([^<]+)", desc)
        location_raw = loc_match.group(1).strip() if loc_match else ""

    pub_date = None
    pub_str = item.findtext("pubDate")
    if pub_str:
        try:
            pub_date = parsedate_to_datetime(pub_str)
        except Exception:
            pass

    description = item.findtext("description") or ""
    # Strip HTML tags from description
    description = re.sub(r"<[^>]+>", " ", description).strip()

    return RawJobPosting(
        connector_name="indeed",
        source_target_id=source_target_id,
        external_id=external_id,
        title=title,
        company=company or "Unknown",
        url=link,
        location=location_raw or None,
        posted_at=pub_date,
        raw_description=description or None,
        metadata={"source": "indeed_rss"},
    )


class IndeedConnector:
    name = "indeed"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles if query.preferred_titles else ["software engineer"]
        location = target.config.get("location", "United States")
        cap = min(query.max_results_per_target or _MAX_PER_QUERY, _MAX_PER_QUERY)

        seen_ids: set[str] = set()
        postings: list[RawJobPosting] = []

        for title in titles:
            for start in range(0, cap, _PAGE_SIZE):
                items = _fetch_rss(title, location, start)
                if not items:
                    break
                for item in items:
                    posting = _parse_item(item, target.id)
                    if posting and posting.external_id not in seen_ids:
                        seen_ids.add(posting.external_id)
                        postings.append(posting)
                if len(items) < _PAGE_SIZE:
                    break
                time.sleep(0.5)

            if len(postings) >= cap:
                break

        log.info("Indeed: %d jobs from %d title(s)", len(postings[:cap]), len(titles))
        return postings[:cap]
