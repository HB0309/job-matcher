"""
Dice connector.

Uses Playwright (headless Chromium) with stealth settings to render
Dice's SPA and extract job cards from the DOM. Description is fetched
via httpx from the SSR detail page (no extra Playwright needed).
"""
import logging
import re
import time
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .base import JobQuery, RawJobPosting, SourceTargetDTO

log = logging.getLogger(__name__)

_SEARCH_BASE = "https://www.dice.com/jobs"
_DETAIL_BASE = "https://www.dice.com/job-detail"
_PAGE_TIMEOUT = 30_000  # ms
_MAX_JOBS = 200
_PAGE_SIZE = 20
_DESC_BATCH = 50   # max descriptions to fetch per run
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def _fetch_description(guid: str) -> str | None:
    """Fetch job description from Dice detail page via httpx (SSR page)."""
    try:
        r = httpx.get(
            f"{_DETAIL_BASE}/{guid}",
            headers=_HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        el = soup.find(class_=re.compile(r"jobDescription", re.I))
        if not el:
            el = soup.find(class_=re.compile(r"description", re.I))
        return el.get_text(separator="\n").strip() if el else None
    except Exception as exc:
        log.debug("Dice: description fetch failed for %s: %s", guid, exc)
        return None

# JS run inside the browser to extract job cards from the rendered DOM
_EXTRACT_JS = """() => {
    const cards = document.querySelectorAll('[data-testid="job-card"]');
    return Array.from(cards).map(card => {
        const guid = card.getAttribute('data-job-guid') || '';

        // Title from aria-label on the invisible overlay link
        const overlayLink = card.querySelector('[data-testid="job-search-job-card-link"]');
        let title = '';
        if (overlayLink) {
            const label = overlayLink.getAttribute('aria-label') || '';
            // Format: "View Details for <Title> (<hash>)"
            title = label.replace(/^View Details for /, '').replace(/ \\([a-f0-9]+\\)$/, '').trim();
        }

        // Company: anchor that links to a company-profile page (pick the one with text)
        const companyAnchors = Array.from(card.querySelectorAll('a[href*="company-profile"]'));
        const companyAnchor = companyAnchors.find(a => a.textContent.trim().length > 0);
        let company = companyAnchor ? companyAnchor.textContent.trim() : '';

        // Location and posted-date live in small text spans
        // Location looks like "City, ST", "Remote", "Hybrid", "On-Site"
        // Date looks like "Today", "Yesterday", "3 days ago"
        const spans = Array.from(card.querySelectorAll('span, p, time'));
        let location = null;
        let postedRaw = null;
        for (const s of spans) {
            const t = s.textContent.trim();
            if (!postedRaw && /^(Today|Yesterday|\\d+ (hour|day|week)s? ago)$/i.test(t)) {
                postedRaw = t;
                continue;
            }
            if (!location && /^(Remote|Hybrid|On-Site|[A-Z][a-zA-Z\\s]+,\\s*[A-Z]{2})$/.test(t)) {
                location = t;
            }
        }

        // Employment type
        let employmentType = null;
        for (const s of spans) {
            const t = s.textContent.trim();
            if (/^(Full.?time|Part.?time|Contract|Third.?Party|Internship)$/i.test(t)) {
                employmentType = t;
                break;
            }
        }

        return { guid, title, company, location, postedRaw, employmentType,
                 url: guid ? 'https://www.dice.com/job-detail/' + guid : '' };
    });
}"""


def _posted_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    now = datetime.now(timezone.utc)
    raw = raw.lower()
    if "today" in raw:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "yesterday" in raw:
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.match(r"(\d+)\s*(hour|day|week)", raw)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(hours=n) if unit == "hour" else timedelta(days=n) if unit == "day" else timedelta(weeks=n)
        return now - delta
    return None


def _parse_card(card: dict, source_target_id: str, description: str | None = None) -> RawJobPosting | None:
    job_id = card.get("guid", "")
    title = (card.get("title") or "").strip()
    url = card.get("url", "")
    if not job_id or not title or not url:
        return None

    return RawJobPosting(
        connector_name="dice",
        source_target_id=source_target_id,
        external_id=job_id,
        title=title,
        company=(card.get("company") or "Unknown").strip() or "Unknown",
        url=url,
        location=card.get("location"),
        posted_at=_posted_date(card.get("postedRaw")),
        raw_description=description,
        employment_type=card.get("employmentType"),
        metadata={"tags": [], "source": "dice_playwright"},
    )


def _scrape_title(title: str, cap: int) -> list[dict]:
    """Render Dice search for one title and extract job cards from DOM."""
    cards: list[dict] = []
    page_num = 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()

        while len(cards) < cap:
            url = (
                f"{_SEARCH_BASE}?q={title.replace(' ', '+')}"
                f"&countryCode=US&radius=30&radiusUnit=mi"
                f"&page={page_num}&pageSize={_PAGE_SIZE}&language=en"
            )
            log.info("Dice: fetching page %d for %r", page_num, title)
            try:
                page.goto(url, timeout=_PAGE_TIMEOUT, wait_until="networkidle")
            except Exception as exc:
                log.warning("Dice: page load error (p=%d): %s", page_num, exc)
                break

            page.wait_for_timeout(1500)
            page_cards = page.evaluate(_EXTRACT_JS)

            if not page_cards:
                log.info("Dice: no cards on page %d, stopping", page_num)
                break

            cards.extend(page_cards)
            log.info("Dice: page %d → %d cards (total %d)", page_num, len(page_cards), len(cards))

            if len(page_cards) < _PAGE_SIZE:
                break  # last page
            page_num += 1
            page.wait_for_timeout(1000)

        browser.close()

    return cards[:cap]


class DiceConnector:
    name = "dice"

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        titles = query.preferred_titles or ["software engineer"]
        cap = min(query.max_results_per_target or _MAX_JOBS, _MAX_JOBS)

        seen_ids: set[str] = set()
        raw_cards: list[dict] = []

        for title in titles:
            if len(raw_cards) >= cap:
                break
            cards = _scrape_title(title, cap - len(raw_cards))
            for card in cards:
                guid = card.get("guid", "")
                if guid and guid not in seen_ids:
                    seen_ids.add(guid)
                    raw_cards.append(card)
            time.sleep(2.0)

        raw_cards = raw_cards[:cap]

        # Fetch descriptions via httpx (SSR pages) — batch limited to _DESC_BATCH
        log.info("Dice: fetching descriptions for %d/%d jobs", min(len(raw_cards), _DESC_BATCH), len(raw_cards))
        for i, card in enumerate(raw_cards[:_DESC_BATCH]):
            card["description"] = _fetch_description(card["guid"])
            if i > 0 and i % 10 == 0:
                time.sleep(1.0)  # gentle rate limit

        postings: list[RawJobPosting] = []
        for card in raw_cards:
            posting = _parse_card(card, target.id, description=card.get("description"))
            if posting:
                postings.append(posting)

        log.info("Dice: %d jobs from %d title(s)", len(postings), len(titles))
        return postings
