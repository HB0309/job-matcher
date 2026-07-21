"""Playwright-based auto-apply worker.

Flow:
  1. Load draft + profile + job posting from DB
  2. Launch headful Chromium (visible to user)
  3. Handle account creation / login if needed
  4. Read OTP from Gmail API (OAuth2) if triggered
  5. Extract all form fields on the page
  6. Fill known fields from profile + qa_answers_json
  7. Send unknowns to HuggingFace LLM for answers
  8. Fill every field; leave browser open for user to review + Submit
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import re
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import ApplicationDraft, JobPosting, Profile, SavedJob, TailoredResume

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic field map — (keyword list, answer factory)
# ---------------------------------------------------------------------------

_FIELD_MAP: list[tuple[list[str], object]] = [
    # Personal info
    (["first name"],                   lambda p: settings.apply_first_name),
    (["last name", "surname"],         lambda p: settings.apply_last_name),
    (["phone", "mobile", "cell"],      lambda p: settings.apply_phone),
    (["address line 1", "street"],     lambda p: settings.apply_address_line1),
    (["address line 2"],               lambda p: ""),
    (["city"],                         lambda p: settings.apply_city),
    (["state", "province"],            lambda p: settings.apply_state),
    (["postal", "zip"],                lambda p: settings.apply_postal_code),
    (["country"],                      lambda p: settings.apply_country),
    # Credentials — always use .env values, never let LLM invent these
    (["email", "e-mail"],              lambda p: settings.apply_email),
    (["password", "passwd"],           lambda p: settings.apply_password),
    # Work eligibility
    (["year", "experience"],           lambda p: str(p.years_experience or "")),
    (["authorized", "work", "legal"],  lambda p: "Yes"),
    # Visa sponsorship — user requires H1B sponsorship
    (["sponsor", "sponsorship required", "require visa", "need sponsorship"],
                                       lambda p: "Yes"),
    (["visa type", "type of visa", "visa category", "sponsorship type"],
                                       lambda p: "H1B"),
    (["remote", "relocat"],            lambda p: "Yes"),
    (["previous employee", "rehire"],  lambda p: "No"),
    # Referral source
    (["hear about", "referral source", "how did you"],  lambda p: settings.apply_heard_about),
    # Social / links — LinkedIn from resume; others blank
    (["linkedin"],                     lambda p: settings.apply_linkedin_url),
    (["github"],                       lambda p: ""),
    (["website", "portfolio"],         lambda p: ""),
    (["cover letter"],                 lambda p: ""),
    # Consent / policy checkboxes
    (["privacy", "consent", "terms", "agree", "acknowledge"], lambda p: "yes"),
    # Education — always answer with most recent (Masters) degree
    (["highest degree", "highest level of education", "level of education", "degree earned"],
                                       lambda p: settings.apply_highest_degree),
    (["school", "university", "college", "institution"],
                                       lambda p: settings.apply_school),
    (["major", "field of study", "degree program"],
                                       lambda p: settings.apply_major),
    # EEO / demographic — real answers instead of "Decline"
    (["gender"],                       lambda p: "Male"),
    (["pronoun"],                      lambda p: "He/Him"),
    (["hispanic", "latino"],           lambda p: "No"),
    (["ethnicity", "race"],            lambda p: "Asian"),
    (["veteran"],                      lambda p: "I am not a protected veteran"),
    (["disability"],                   lambda p: "No, I do not have a disability and have not had one in the past"),
    # Date fields (e.g. Self-Identify disability form requires today's date)
    (["date"],                         lambda p: datetime.date.today().isoformat()),
]


def _match_field(label: str) -> str | None:
    low = label.lower()
    for keywords, factory in _FIELD_MAP:
        if any(k in low for k in keywords):
            return factory  # type: ignore[return-value]
    return None


def _closest_option(answer: str, options: list[str]) -> str:
    if not options:
        return answer
    best = max(options, key=lambda o: SequenceMatcher(None, answer.lower(), o.lower()).ratio())
    return best


# ---------------------------------------------------------------------------
# Gmail API OTP reader (OAuth2 — no password)
# ---------------------------------------------------------------------------

_TOKEN_FILE = Path(__file__).parent.parent.parent / "gmail_token.json"
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_gmail_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not _TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"Gmail token not found at {_TOKEN_FILE}. "
            "Run: python gmail_auth_setup.py"
        )
    creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _decode_gmail_body(payload: dict) -> str:
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                return base64.urlsafe_b64decode(data + "==").decode(errors="replace")
    data = payload.get("body", {}).get("data", "")
    return base64.urlsafe_b64decode(data + "==").decode(errors="replace") if data else ""


def _fetch_otp_from_gmail(timeout: int = 60) -> str | None:
    logger.info("auto_apply: polling Gmail API for OTP (timeout=%ds)", timeout)
    try:
        service = _get_gmail_service()
    except Exception as exc:
        logger.warning("auto_apply: Gmail API unavailable: %s", exc)
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = service.users().messages().list(
                userId="me", labelIds=["INBOX"], q="is:unread", maxResults=5
            ).execute()
            messages = result.get("messages", [])
            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="full"
                ).execute()
                body = _decode_gmail_body(msg.get("payload", {}))
                m = re.search(r'\b\d{4,8}\b', body)
                if m:
                    logger.info("auto_apply: OTP found: %s", m.group())
                    return m.group()
        except Exception as exc:
            logger.warning("auto_apply: Gmail poll error: %s", exc)
        time.sleep(3)

    logger.warning("auto_apply: OTP not found within timeout")
    return None


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

_APPLY_BUTTON_TEXTS = [
    "Apply Now", "Apply For This Job", "Apply for Job", "Apply Online",
    "Apply", "Start Application", "Submit Application", "Easy Apply",
]

# Workday "Start Your Application" dialog — shown after clicking Apply
_WORKDAY_DIALOG_BUTTONS = [
    "Apply Manually",
    "Autofill with Resume",
    "Use My Last Application",
]

# Fields whose labels indicate honeypot / bot-trap — skip these entirely
_HONEYPOT_PATTERNS = [
    "for robots only", "do not enter", "honeypot", "bot trap",
    "leave blank", "leave this blank", "leave empty",
]


def _is_honeypot_field(label: str) -> bool:
    low = label.lower()
    return any(p in low for p in _HONEYPOT_PATTERNS)


def _dismiss_workday_dialog(page) -> bool:
    """Click 'Apply Manually' (or similar) if Workday's start-application dialog is open."""
    for btn_text in _WORKDAY_DIALOG_BUTTONS:
        try:
            loc = page.locator(f"button:has-text('{btn_text}')").first
            if loc.is_visible(timeout=1500):
                logger.info("auto_apply: dismissing Workday start-dialog via %r", btn_text)
                loc.click()
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    return False


def _click_apply_button(page) -> bool:
    """Click the Apply button on a job listing page. Returns True if found."""
    # Try Playwright locators first (handle JS-rendered elements)
    for text in _APPLY_BUTTON_TEXTS:
        for tag in ("button", "a"):
            try:
                loc = page.locator(f"{tag}:has-text('{text}')").first
                if loc.is_visible(timeout=3000):
                    logger.info("auto_apply: clicking Apply button: %r", text)
                    loc.click()
                    page.wait_for_timeout(3000)
                    # Dismiss Workday's "Start Your Application" dialog if it appeared
                    _dismiss_workday_dialog(page)
                    return True
            except Exception:
                continue

    # Fallback: data-automation-id (Workday-specific)
    for attr in ["applyButton", "applyNowButton", "apply-now", "apply-button"]:
        try:
            loc = page.locator(f"[data-automation-id='{attr}']").first
            if loc.is_visible(timeout=1000):
                logger.info("auto_apply: clicking Workday apply button (data-automation-id=%s)", attr)
                loc.click()
                page.wait_for_timeout(3000)
                _dismiss_workday_dialog(page)
                return True
        except Exception:
            continue

    return False



def _extract_fields(page) -> list[dict]:
    fields = []
    seen_selectors: set[str] = set()

    # Strategy 1: standard <label for="id"> + <input id="id">
    for label_el in page.query_selector_all("label"):
        label_text = (label_el.inner_text() or "").strip()
        if not label_text:
            continue
        if _is_honeypot_field(label_text):
            logger.info("auto_apply: skipping honeypot field: %r", label_text)
            continue

        input_el = None
        for_id = label_el.get_attribute("for")
        if for_id:
            input_el = page.query_selector(f"#{for_id}")
        if not input_el:
            input_el = label_el.query_selector("input, textarea, select")
        if not input_el:
            try:
                h = page.evaluate_handle(
                    "(el) => el.nextElementSibling?.matches('input,textarea,select') ? el.nextElementSibling : null",
                    label_el,
                )
                if h and h.as_element():
                    input_el = h
            except Exception:
                pass

        if not input_el:
            continue

        field = _build_field(page, input_el, label_text, seen_selectors)
        if field:
            fields.append(field)

    # Strategy 2: inputs with aria-label or placeholder (no <label> element)
    for input_el in page.query_selector_all("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select"):
        label_text = (
            input_el.get_attribute("aria-label")
            or input_el.get_attribute("placeholder")
            or input_el.get_attribute("name")
            or ""
        ).strip()
        if not label_text:
            continue
        if _is_honeypot_field(label_text):
            logger.info("auto_apply: skipping honeypot field: %r", label_text)
            continue
        field = _build_field(page, input_el, label_text, seen_selectors)
        if field:
            fields.append(field)

    # Strategy 3a: Workday date spinbutton groups
    # Detected via dateSectionMonth-input; calendar button fills the whole group.
    cal_index = 0
    for month_input in page.query_selector_all('[data-automation-id="dateSectionMonth-input"]'):
        try:
            label_text = page.evaluate("""el => {
                let node = el;
                for (let i = 0; i < 8; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    const role = node.getAttribute('role');
                    if (role === 'group' || node.tagName === 'FIELDSET') {
                        // First non-empty text child that's short (the label)
                        for (const child of node.children) {
                            const t = child.textContent.replace(/\\*/g,'').trim();
                            if (t && t.length < 60 && !t.includes('/')) return t;
                        }
                    }
                }
                return 'Date';
            }""", month_input)
            label_clean = (label_text or "Date").strip()
            uid = f"__workday_date_{cal_index}__"
            if uid in seen_selectors:
                cal_index += 1
                continue
            seen_selectors.add(uid)
            fields.append({
                "label": label_clean,
                "type": "workday_date",
                "options": [],
                "selector": uid,
                "name": "",
                "calendar_index": cal_index,
            })
            cal_index += 1
        except Exception as exc:
            logger.debug("auto_apply: workday date extraction error: %s", exc)

    # Strategy 3b: file inputs (resume / transcript uploads)
    for file_input in page.query_selector_all("input[type='file']"):
        try:
            # Find label via aria-label, id, or nearby label element
            label_text = (
                file_input.get_attribute("aria-label")
                or file_input.get_attribute("name")
                or ""
            )
            if not label_text:
                input_id = file_input.get_attribute("id") or ""
                if input_id:
                    lbl = page.query_selector(f"label[for='{input_id}']")
                    if lbl:
                        label_text = (lbl.inner_text() or "").strip()
            if not label_text:
                label_text = page.evaluate("""el => {
                    let node = el.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!node) break;
                        const lbl = node.querySelector('label, [role="heading"], p');
                        if (lbl) return lbl.textContent.replace(/\\*/g,'').trim();
                        node = node.parentElement;
                    }
                    return 'Upload File';
                }""", file_input)
            label_clean = (label_text or "Upload File").strip()
            selector = file_input.evaluate(
                "el => el.id ? `#${CSS.escape(el.id)}` : el.name ? `input[name='${el.name}']` : null"
            )
            if not selector or selector in seen_selectors:
                continue
            seen_selectors.add(selector)
            fields.append({
                "label": label_clean,
                "type": "file",
                "options": [],
                "selector": selector,
                "name": file_input.get_attribute("name") or "",
            })
        except Exception as exc:
            logger.debug("auto_apply: file input extraction error: %s", exc)

    # Strategy 3c: Workday-style ARIA listbox buttons (custom dropdowns)
    # Pattern: a <button> whose accessible name ends with "Required" and contains "Select One"
    # or is adjacent to a label element. Extract label from button text before "Select One".
    for btn in page.query_selector_all("button"):
        try:
            btn_text = (btn.inner_text() or "").strip()
            aria_name = (btn.get_attribute("aria-label") or "").strip()
            full_name = aria_name or btn_text

            # Skip if this doesn't look like a Workday dropdown
            if "select one" not in full_name.lower() and not btn.get_attribute("aria-haspopup"):
                continue

            # Skip nav/header buttons (e.g. hamburger menu, language selector)
            in_nav = page.evaluate("""el => {
                let node = el;
                while (node) {
                    const tag = node.tagName ? node.tagName.toLowerCase() : '';
                    if (tag === 'nav' || tag === 'header') return true;
                    const role = (node.getAttribute && node.getAttribute('role')) || '';
                    if (role === 'navigation' || role === 'banner') return true;
                    const aid = (node.getAttribute && node.getAttribute('data-automation-id')) || '';
                    if (aid === 'hammyMenuIcon' || aid === 'navigationHeader' || aid === 'siteHeader') return true;
                    node = node.parentElement;
                }
                return false;
            }""", btn)
            if in_nav:
                continue

            # Try to find a label in the parent container
            label_text = ""
            try:
                label_text = page.evaluate("""el => {
                    const parent = el.closest('[class]') || el.parentElement;
                    if (!parent) return '';
                    // Look for a sibling or child that is a label-like element
                    const prev = el.previousElementSibling;
                    if (prev) return prev.textContent.trim();
                    const firstChild = parent.firstElementChild;
                    if (firstChild && firstChild !== el) return firstChild.textContent.trim();
                    return '';
                }""", btn)
            except Exception:
                pass

            # Fallback: strip "Select One", "Required", and current value from button aria-name
            if not label_text and "select one" in full_name.lower():
                label_text = full_name.lower().replace("select one", "").replace("required", "").strip()
                label_text = label_text.title()

            if not label_text:
                continue
            # Strip trailing asterisk
            label_text = label_text.rstrip("*").strip()

            if _is_honeypot_field(label_text):
                continue

            selector = btn.evaluate(
                "el => el.id ? `#${CSS.escape(el.id)}` : null"
            )
            if not selector:
                # Use a unique attribute if available
                aria_controls = btn.get_attribute("aria-controls")
                if aria_controls:
                    selector = f"button[aria-controls='{aria_controls}']"
                else:
                    # Fallback: use button text as a locator hint stored separately
                    selector = f"__workday_btn__{full_name}"

            if selector in seen_selectors:
                continue
            seen_selectors.add(selector)

            fields.append({
                "label": label_text,
                "type": "workday_dropdown",
                "options": [],
                "selector": selector,
                "name": full_name,  # full button aria-name, used when filling
            })
        except Exception as exc:
            logger.debug("auto_apply: workday dropdown extraction error: %s", exc)

    return fields


def _build_field(page, input_el, label_text: str, seen: set) -> dict | None:
    try:
        tag = input_el.evaluate("el => el.tagName.toLowerCase()")
        input_type = (input_el.get_attribute("type") or "text").lower()

        selector = input_el.evaluate(
            "el => el.id ? `#${CSS.escape(el.id)}` : el.name ? `[name='${el.name}']` : null"
        )
        if not selector or selector in seen:
            return None
        seen.add(selector)

        options: list[str] = []
        if tag == "select":
            options = input_el.evaluate(
                "el => Array.from(el.options).map(o => o.text.trim()).filter(t => t && t !== '--')"
            )
            field_type = "select"
        elif input_type == "radio":
            field_type = "radio"
            name = input_el.get_attribute("name") or ""
            for r in page.query_selector_all(f"input[type='radio'][name='{name}']"):
                try:
                    lbl = r.get_attribute("value") or ""
                    parent_lbl = page.evaluate_handle("el => el.closest('label')", r)
                    if parent_lbl and parent_lbl.as_element():
                        lbl = (parent_lbl.inner_text() or lbl).strip()
                    if lbl:
                        options.append(lbl)
                except Exception:
                    pass
        elif input_type == "checkbox":
            field_type = "checkbox"
        elif tag == "textarea":
            field_type = "textarea"
        else:
            field_type = input_type

        return {
            "label": label_text,
            "type": field_type,
            "options": options,
            "selector": selector,
            "name": input_el.get_attribute("name") or "",
        }
    except Exception as exc:
        logger.debug("auto_apply: _build_field error: %s", exc)
        return None


def _click_radio(page, name: str, answer: str, options: list[str]) -> None:
    target = _closest_option(answer, options) if options else answer
    radios = page.query_selector_all(f"input[type='radio'][name='{name}']")
    for r in radios:
        lbl = page.evaluate_handle("(el) => el.closest('label') || el.previousElementSibling", r)
        txt = (lbl.inner_text() if lbl.as_element() else "").strip()
        if txt.lower() == target.lower():
            r.click()
            return
    if radios:
        radios[0].click()


def _fill_workday_dropdown(page, field: dict, answer: str) -> None:
    """Click a Workday ARIA listbox button and select the closest matching option."""
    sel = field["selector"]
    full_name = field.get("name", "")
    try:
        # Click the button to open the listbox
        if sel.startswith("__workday_btn__"):
            btn = page.locator(f"button:has-text('{full_name[:40]}')").first
        else:
            btn = page.locator(sel).first
        btn.click()
        page.wait_for_timeout(600)

        # Collect visible options from any open listbox
        options = page.query_selector_all("li[role='option'], [role='listbox'] [role='option'], [role='option']")
        if not options:
            # Try typing into a search box if present (Workday "State" has a search input)
            search = page.query_selector("[role='listbox'] input, [role='combobox'] input")
            if search:
                search.fill(answer)
                page.wait_for_timeout(600)
                options = page.query_selector_all("li[role='option'], [role='option']")

        option_texts = []
        for opt in options:
            try:
                option_texts.append((opt.inner_text().strip(), opt))
            except Exception:
                pass

        if not option_texts:
            logger.warning("auto_apply: no options found for workday dropdown %r", field["label"])
            page.keyboard.press("Escape")
            return

        best_text = _closest_option(answer, [t for t, _ in option_texts])
        for text, opt in option_texts:
            if text == best_text:
                opt.click()
                page.wait_for_timeout(400)
                return

        # Fallback: click first non-placeholder option
        option_texts[0][1].click()
        page.wait_for_timeout(400)
    except Exception as exc:
        logger.warning("auto_apply: workday dropdown fill failed for %r: %s", field["label"], exc)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass


def _fill_workday_month_year_calendar(page, target: datetime.date) -> None:
    """Navigate a Workday year-month picker and click the target month.

    This calendar style shows Previous Year / Next Year navigation and a
    grid of 12 month buttons (Jan–Dec) for the current year.
    """
    month_name = target.strftime("%B")  # "May", "February", etc.

    for _ in range(12):
        # Read current year from the calendar header
        current_year = page.evaluate("""() => {
            // Find a button labelled "Previous Year" and look at its sibling for the year
            const all = Array.from(document.querySelectorAll('button'));
            const prev = all.find(b =>
                (b.textContent || '').includes('Previous Year') ||
                (b.getAttribute('aria-label') || '').includes('Previous Year')
            );
            if (!prev) return 0;
            const parent = prev.parentElement;
            if (!parent) return 0;
            for (const child of parent.children) {
                const t = child.textContent.trim();
                if (/^\\d{4}$/.test(t)) return parseInt(t, 10);
            }
            return 0;
        }""")

        if not current_year:
            break
        if current_year == target.year:
            break
        elif current_year > target.year:
            prev_btn = page.locator("button:has-text('Previous Year')").first
            if not prev_btn.is_visible(timeout=600):
                break
            prev_btn.click()
        else:
            next_btn = page.locator("button:has-text('Next Year')").first
            if not next_btn.is_visible(timeout=600):
                break
            next_btn.click()
        page.wait_for_timeout(300)

    # Click the target month — month buttons are labelled e.g. "May 2025" or "Selected May 2025"
    # Use partial text match to find the month regardless of "Selected" prefix
    month_buttons = page.query_selector_all(f"button[aria-label*='{month_name} {target.year}'], button:has-text('{month_name}')")
    for btn in month_buttons:
        label = btn.get_attribute("aria-label") or btn.inner_text() or ""
        if month_name in label and str(target.year) in label:
            page.evaluate("el => el.scrollIntoView({block:'center'})", btn)
            btn.click()
            page.wait_for_timeout(400)
            return

    # Fallback: find month by position in Month Picker list
    try:
        month_index = target.month - 1  # 0-based
        month_list_items = page.query_selector_all("ul[aria-label='Month Picker'] li, [role='list'] li")
        if len(month_list_items) == 12:
            page.evaluate("el => el.scrollIntoView({block:'center'})", month_list_items[month_index])
            month_list_items[month_index].click()
            page.wait_for_timeout(400)
    except Exception as exc:
        logger.debug("auto_apply: month fallback click failed: %s", exc)


def _calendar_navigate_to(page, target: datetime.date) -> None:
    """Navigate an open Workday day-level calendar to the month/year of target."""
    for _ in range(24):
        month_text = page.evaluate("""() => {
            // Look for a text node matching "Month YYYY" pattern anywhere in the document
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const t = node.textContent.trim();
                if (/^[A-Z][a-z]+ \\d{4}$/.test(t)) return t;
            }
            return '';
        }""")
        if not month_text:
            break
        try:
            cal_first = datetime.datetime.strptime(month_text, "%B %Y").date().replace(day=1)
        except ValueError:
            break
        target_first = target.replace(day=1)
        if cal_first == target_first:
            break
        # Find prev/next navigation buttons (not month picker buttons)
        if cal_first < target_first:
            nav = page.locator("button[aria-label='Next Month'], button:has-text('Next Month')").first
        else:
            nav = page.locator("button[aria-label='Previous Month'], button:has-text('Previous Month')").first
        if nav.is_visible(timeout=400):
            nav.click()
        else:
            break
        page.wait_for_timeout(300)


def _calendar_click_day(page, target: datetime.date) -> None:
    """Click a specific day in an open Workday day-level calendar."""
    month_name = target.strftime("%B %Y")

    def _find_day_btn(day: int):
        ds = str(day)
        for btn in page.query_selector_all("button"):
            label = btn.get_attribute("aria-label") or ""
            if month_name in label and ds in label.split():
                return btn
        return None

    btn = _find_day_btn(target.day)
    if not btn:
        logger.warning("auto_apply: calendar day %d not found in %s", target.day, month_name)
        page.keyboard.press("Escape")
        return

    label = btn.get_attribute("aria-label") or ""
    if "selected" in label.lower():
        # Already selected — click neighbor first to trigger React onChange
        neighbor_day = target.day + 1 if target.day < 28 else target.day - 1
        neighbor = _find_day_btn(neighbor_day)
        if neighbor:
            page.evaluate("el => el.scrollIntoView({block:'center'})", neighbor)
            neighbor.click()
            page.wait_for_timeout(400)
            cal_btn = (
                page.query_selector('[data-automation-id="dateIcon"]')
                or page.query_selector('[aria-label="Calendar"]')
            )
            if cal_btn:
                page.evaluate("el => el.scrollIntoView({block:'center'})", cal_btn)
                cal_btn.click()
                page.wait_for_timeout(600)
            btn = _find_day_btn(target.day)
            if not btn:
                return

    page.evaluate("el => el.scrollIntoView({block:'center'})", btn)
    btn.click()


def _fill_workday_date_via_calendar(page, answer: str, calendar_index: int = 0) -> None:
    """Fill a Workday date field by opening the calendar picker.

    answer: ISO date "YYYY-MM-DD", "MM/DD/YYYY", or "today".
    calendar_index: which calendar icon button to click (0-based).
    Supports both year-month pickers (Previous/Next Year + month grid) and
    day-level pickers (Previous/Next Month + day grid).
    """
    try:
        if not answer or answer.lower() == "today":
            target = datetime.date.today()
        else:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
                try:
                    target = datetime.datetime.strptime(answer[:10], fmt).date()
                    break
                except ValueError:
                    pass
            else:
                target = datetime.date.today()

        # Find the Nth calendar icon button on the page
        cal_btns = page.query_selector_all('[data-automation-id="dateIcon"]')
        if not cal_btns:
            cal_btns = page.query_selector_all('[aria-label="Calendar"]')
        if not cal_btns:
            logger.warning("auto_apply: no calendar buttons found")
            return

        idx = min(calendar_index, len(cal_btns) - 1)
        cal_btn = cal_btns[idx]
        page.evaluate("el => el.scrollIntoView({block:'center'})", cal_btn)
        cal_btn.click()
        page.wait_for_timeout(700)

        # Detect calendar type: year-month picker (Previous/Next Year) vs day picker
        has_year_nav = bool(page.query_selector(
            "button:has-text('Previous Year'), button[aria-label='Previous Year']"
        ))
        if has_year_nav:
            _fill_workday_month_year_calendar(page, target)
        else:
            _calendar_navigate_to(page, target)
            _calendar_click_day(page, target)
        page.wait_for_timeout(400)

    except Exception as exc:
        logger.warning("auto_apply: _fill_workday_date_via_calendar failed: %s", exc)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# LaTeX resume parser — extracts structured data from tailored .tex source
# ---------------------------------------------------------------------------

def _parse_latex_resume(latex: str) -> dict:
    """Parse a tailored .tex file and return work_experience, education, skills."""
    import re as _re

    result: dict = {"work_experience": [], "education": [], "skills": []}

    # ── Work Experience ───────────────────────────────────────────────────────
    # Pattern:
    #   \textbf{TITLE} \hfill \textit{LOCATION}\\
    #   COMPANY \hfill \textit{START – END}
    work_sec = _re.search(
        r'\\begin\{rSection\}\{Work Experience\}(.*?)\\end\{rSection\}',
        latex, _re.DOTALL
    )
    if work_sec:
        wtext = work_sec.group(1)
        job_pat = _re.compile(
            r'\\textbf\{([^}]+)\}\s*\\hfill\s*\\textit\{([^}]+)\}\s*\\\\\s*\n'
            r'([^\\\n]+?)\s*\\hfill\s*\\textit\{([^}]+)\}',
            _re.MULTILINE,
        )
        for m in job_pat.finditer(wtext):
            title, location, company, dates = (g.strip() for g in m.groups())
            parts = _re.split(r'\s*[–—]\s*|--', dates)
            start = parts[0].strip() if parts else ""
            end = parts[1].strip() if len(parts) > 1 else "Present"

            # Extract bullets for this job
            job_start = m.start()
            next_job = job_pat.search(wtext, m.end())
            block = wtext[job_start: next_job.start() if next_job else len(wtext)]
            bullets = _re.findall(r'\\item\s+(.*?)(?=\\item|\n\s*\n|\\end\{itemize\})', block, _re.DOTALL)
            cleaned = []
            for b in bullets:
                b = _re.sub(r'\\textbf\{([^}]+)\}', r'\1', b)
                b = _re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', b)
                b = b.strip()
                if b:
                    cleaned.append(b)

            result["work_experience"].append({
                "title": title,
                "company": company,
                "location": location,
                "start": start,
                "end": end,
                "bullets": cleaned[:5],
            })

    # ── Education ─────────────────────────────────────────────────────────────
    # Pattern:
    #   {\bf SCHOOL} \hfill \textit{LOCATION}\\
    #   DEGREE \hfill \textit{GRAD_DATE}\\
    edu_sec = _re.search(
        r'\\begin\{rSection\}\{Education\}(.*?)\\end\{rSection\}',
        latex, _re.DOTALL
    )
    if edu_sec:
        etext = edu_sec.group(1)
        edu_pat = _re.compile(
            r'\{\\bf\s+([^}]+)\}\s*\\hfill\s*\\textit\{([^}]+)\}\s*\\\\\s*\n'
            r'([^\\\n]+?)\s*\\hfill\s*\\textit\{([^}]+)\}',
            _re.MULTILINE,
        )
        for m in edu_pat.finditer(etext):
            school, location, degree, end_date = (g.strip() for g in m.groups())
            result["education"].append({
                "school": school,
                "degree": degree,
                "location": location,
                "end": end_date,
            })

    # ── Skills ────────────────────────────────────────────────────────────────
    skills_sec = _re.search(
        r'\\begin\{rSection\}\{Technical Skills\}(.*?)\\end\{rSection\}',
        latex, _re.DOTALL
    )
    if skills_sec:
        stext = skills_sec.group(1)
        skill_lines = _re.findall(r'&\s*([^\\&\n]+?)(?:\s*\\\\|\s*$)', stext, _re.MULTILINE)
        flat: list[str] = []
        for line in skill_lines:
            for s in line.split(","):
                s = s.strip()
                if s and len(s) < 60:
                    flat.append(s)
        result["skills"] = flat

    logger.info(
        "auto_apply: parsed LaTeX — %d jobs, %d edu, %d skills",
        len(result["work_experience"]), len(result["education"]), len(result["skills"])
    )
    return result


# ---------------------------------------------------------------------------
# Workday section fillers — experience, education, skills
# ---------------------------------------------------------------------------

def _workday_find_section_add_btn(page, section_keywords: list[str]):
    """Find an Add button inside a named Workday section. Returns locator or None."""
    for kw in section_keywords:
        try:
            # Look for a heading that contains the keyword, then find a nearby Add button
            section = page.locator(f"h3:has-text('{kw}'), h4:has-text('{kw}'), [role='heading']:has-text('{kw}')").first
            if not section.is_visible(timeout=800):
                continue
            # Search the section's parent for an Add button
            parent = page.evaluate_handle("el => el.closest('section') || el.parentElement?.parentElement?.parentElement", section.element_handle())
            if parent and parent.as_element():
                add = parent.as_element().query_selector("button:has-text('Add'), [data-automation-id*='Add']")
                if add:
                    return page.locator(f"button:has-text('Add')").nth(
                        len(page.query_selector_all("button:has-text('Add')")) - 1
                    )
            # Fallback: any visible Add button after the heading
            add_btns = page.locator("button:has-text('Add')").all()
            if add_btns:
                return add_btns[-1]
        except Exception:
            pass
    return None


def _workday_click_section_add(page, section_name: str) -> bool:
    """Click the 'Add' button in a Workday section. Returns True if found."""
    try:
        # Strategy: find Add button after the section heading in DOM order.
        # Use exact text match for the heading to avoid matching sub-entry headings
        # like "Work Experience 1" when looking for "Work Experience".
        clicked = page.evaluate(f"""(secName) => {{
            const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
            // Prefer exact match first, fall back to contains
            const exact = headings.filter(h => h.textContent.trim().toLowerCase() === secName.toLowerCase());
            const candidates = exact.length ? exact : headings.filter(h => {{
                const t = h.textContent.trim().toLowerCase();
                return t.startsWith(secName.toLowerCase()) && !(/\\d$/.test(t));
            }});
            for (const h of candidates) {{
                let node = h;
                for (let i = 0; i < 6; i++) {{
                    node = node.parentElement;
                    if (!node) break;
                    const addBtn = Array.from(node.querySelectorAll('button')).find(
                        b => b.textContent.trim() === 'Add' || b.textContent.trim().startsWith('Add ')
                    );
                    if (addBtn && addBtn.offsetParent !== null) {{
                        addBtn.scrollIntoView({{block:'center'}});
                        addBtn.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }}""", section_name)
        return bool(clicked)
    except Exception as exc:
        logger.debug("auto_apply: _workday_click_section_add failed: %s", exc)
        return False


def _workday_fill_text_field(page, selectors_or_labels: list[str], value: str) -> bool:
    """Try to fill a text field by selector or aria-label. Returns True if filled."""
    for sel in selectors_or_labels:
        try:
            el = (
                page.query_selector(sel)
                or page.query_selector(f"input[aria-label*='{sel}'], textarea[aria-label*='{sel}']")
                or page.query_selector(f"[data-automation-id*='{sel}']")
            )
            if el and el.is_visible():
                el.scroll_into_view_if_needed()
                el.fill(value)
                page.keyboard.press("Tab")
                page.wait_for_timeout(200)
                return True
        except Exception:
            pass
    return False


def _workday_fill_month_year(page, month: str, year: str, field_prefix: str = "") -> None:
    """Fill a month/year date pair. Handles both dropdown and spinbutton styles."""
    month_int = int(month)
    year_int = int(year)
    # Try spinbutton (date picker) approach first
    month_input = page.query_selector(
        f'[data-automation-id="{field_prefix}dateSectionMonth-input"]'
        if field_prefix else '[data-automation-id="dateSectionMonth-input"]'
    )
    if month_input:
        target = datetime.date(year_int, month_int, 1)
        _fill_workday_date_via_calendar(page, target.isoformat())
        return

    # Try Month/Year dropdown approach
    for month_sel in ["[data-automation-id*='month']", "select[name*='month']", "select[id*='month']"]:
        el = page.query_selector(month_sel)
        if el and el.evaluate("e => e.tagName") == "SELECT":
            page.select_option(month_sel, index=month_int - 1)
            break

    for year_sel in ["[data-automation-id*='year']", "select[name*='year']", "select[id*='year']"]:
        el = page.query_selector(year_sel)
        if el and el.evaluate("e => e.tagName") == "SELECT":
            page.select_option(year_sel, value=str(year_int))
            break


def _workday_save_entry(page) -> bool:
    """Click Save/Done inside an open dialog to commit a sub-form entry.

    Workday inline forms (Work Experience, Education on the My Experience step)
    do NOT have per-entry Save buttons — data is saved when the step advances.
    Only click Save if a modal dialog is currently open.
    """
    # Check whether a dialog/modal overlay is open
    dialog = page.query_selector("[role='dialog'], [data-automation-id*='Modal'], [data-automation-id*='Dialog']")
    if not dialog:
        return False  # inline form — no per-entry Save needed

    for text in ("Save", "Done", "OK"):
        try:
            btn = dialog.query_selector(f"button:has-text('{text}')")
            if btn and btn.is_visible():
                page.evaluate("el => el.scrollIntoView({block:'center'})", btn)
                btn.click()
                page.wait_for_timeout(1000)
                return True
        except Exception:
            pass
    return False


def _fill_workday_experience_section(page, experiences: list[dict]) -> None:
    """Add each work experience entry to Workday's Work Experience section."""
    if not experiences:
        return

    # Check if this page has a Work Experience section
    if not page.query_selector("h3:has-text('Work Experience'), h4:has-text('Work Experience'), [role='heading']:has-text('Work Experience')"):
        return

    logger.info("auto_apply: filling Work Experience section (%d entries)", len(experiences))
    for exp in experiences:
        if not _workday_click_section_add(page, "Work Experience"):
            logger.warning("auto_apply: could not find Work Experience Add button")
            break
        page.wait_for_timeout(1500)

        # Fill Job Title
        _workday_fill_text_field(page, [
            "input[data-automation-id='jobTitle']", "jobTitle", "Job Title",
            "input[aria-label*='Job Title']", "input[aria-label*='Title']",
        ], exp["title"])

        # Fill Company
        _workday_fill_text_field(page, [
            "input[data-automation-id='company']", "Company", "Employer",
            "input[aria-label*='Company']", "input[aria-label*='Employer']",
        ], exp["company"])

        # Fill Location
        _workday_fill_text_field(page, [
            "input[data-automation-id='location']", "Location", "City",
            "input[aria-label*='Location']", "input[aria-label*='City']",
        ], exp.get("location", ""))

        # Fill Description from bullets
        description = "\n".join(f"• {b}" for b in exp.get("bullets", []))
        if description:
            _workday_fill_text_field(page, [
                "textarea[data-automation-id='description']",
                "textarea[aria-label*='Description']",
                "textarea[aria-label*='Responsibilities']",
                "textarea",
            ], description)

        # Fill start/end dates using the last two calendar buttons on the page
        # (the most-recently-added entry's From and To calendars).
        cal_btns = page.query_selector_all('[data-automation-id="dateIcon"], [aria-label="Calendar"]')
        n = len(cal_btns)
        if exp.get("start") and n >= 2:
            try:
                start_dt = datetime.datetime.strptime(exp["start"], "%b %Y")
                _fill_workday_date_via_calendar(
                    page, start_dt.date().isoformat(), calendar_index=n - 2
                )
            except (ValueError, Exception) as exc:
                logger.debug("auto_apply: exp start date parse failed: %s", exc)

        if exp.get("end") and exp["end"].lower() != "present" and n >= 1:
            try:
                end_dt = datetime.datetime.strptime(exp["end"], "%b %Y")
                _fill_workday_date_via_calendar(
                    page, end_dt.date().isoformat(), calendar_index=n - 1
                )
            except (ValueError, Exception) as exc:
                logger.debug("auto_apply: exp end date parse failed: %s", exc)

        _workday_save_entry(page)
        page.wait_for_timeout(800)


def _fill_workday_education_section(page) -> None:
    """Add JHU Masters + VIT Bachelors to Workday's Education section using config values."""
    # Check if this page has an Education section
    if not page.query_selector("h3:has-text('Education'), h4:has-text('Education'), [role='heading']:has-text('Education')"):
        return

    educations = [
        {
            "school": settings.apply_edu1_school,
            "degree": settings.apply_edu1_degree,
            "major": settings.apply_edu1_major,
            "start_month": settings.apply_edu1_start_month,
            "start_year": settings.apply_edu1_start_year,
            "end_month": settings.apply_edu1_end_month,
            "end_year": settings.apply_edu1_end_year,
        },
        {
            "school": settings.apply_edu2_school,
            "degree": settings.apply_edu2_degree,
            "major": settings.apply_edu2_major,
            "start_month": settings.apply_edu2_start_month,
            "start_year": settings.apply_edu2_start_year,
            "end_month": settings.apply_edu2_end_month,
            "end_year": settings.apply_edu2_end_year,
        },
    ]

    logger.info("auto_apply: filling Education section (%d entries)", len(educations))
    for edu in educations:
        if not _workday_click_section_add(page, "Education"):
            logger.warning("auto_apply: could not find Education Add button")
            break
        page.wait_for_timeout(1500)

        # School Name — Workday often uses a typeahead; type, wait, pick first result
        school_el = (
            page.query_selector("input[data-automation-id='school']")
            or page.query_selector("input[aria-label*='School']")
            or page.query_selector("input[aria-label*='University']")
            or page.query_selector("input[aria-label*='Institution']")
        )
        if school_el:
            school_el.scroll_into_view_if_needed()
            school_el.fill(edu["school"])
            page.wait_for_timeout(1000)
            # Try to pick the first autocomplete result
            first_opt = page.query_selector("[role='option']:first-child, li[role='option']")
            if first_opt:
                first_opt.click()
                page.wait_for_timeout(400)
            else:
                page.keyboard.press("Tab")

        # Degree dropdown or text
        degree_sel = (
            page.query_selector("select[data-automation-id='degree'], select[aria-label*='Degree']")
            or page.query_selector("input[aria-label*='Degree']")
        )
        if degree_sel:
            tag = degree_sel.evaluate("el => el.tagName")
            if tag == "SELECT":
                page.select_option(
                    degree_sel.evaluate("el => el.id ? '#'+el.id : el.name ? `[name='${el.name}']` : 'select'"),
                    label=_closest_option(edu["degree"], degree_sel.evaluate(
                        "el => Array.from(el.options).map(o => o.text.trim())"
                    ))
                )
            else:
                degree_sel.fill(edu["degree"])
                page.keyboard.press("Tab")

        # Field of Study / Major
        _workday_fill_text_field(page, [
            "input[data-automation-id='fieldOfStudy']",
            "input[aria-label*='Field of Study']",
            "input[aria-label*='Major']",
            "Field of Study", "Major",
        ], edu["major"])

        # Start/End dates — use last two calendar buttons (belong to this entry).
        try:
            start_dt = datetime.date(int(edu["start_year"]), int(edu["start_month"]), 1)
            end_dt = datetime.date(int(edu["end_year"]), int(edu["end_month"]), 1)

            cal_btns = page.query_selector_all('[data-automation-id="dateIcon"], [aria-label="Calendar"]')
            n = len(cal_btns)
            if n >= 2:
                _fill_workday_date_via_calendar(page, start_dt.isoformat(), calendar_index=n - 2)
            if n >= 1:
                _fill_workday_date_via_calendar(page, end_dt.isoformat(), calendar_index=n - 1)
        except Exception as exc:
            logger.debug("auto_apply: education date fill failed: %s", exc)

        _workday_save_entry(page)
        page.wait_for_timeout(800)


def _fill_workday_skills_section(page, skills: list[str]) -> None:
    """Fill the Workday skills chip/tag input with skills from the resume."""
    if not skills:
        return

    # Look for a skills input (chip input, typeahead, or text area)
    skills_input = (
        page.query_selector("input[data-automation-id*='skill'], input[aria-label*='skill' i]")
        or page.query_selector("[data-automation-id='skillsSection'] input")
        or page.query_selector("input[placeholder*='skill' i]")
    )
    if not skills_input:
        # Check if we're even on the My Experience page
        if not page.query_selector("h3:has-text('Skills'), h4:has-text('Skills'), [role='heading']:has-text('Skills')"):
            return
        # Try generic input near Skills heading
        skills_input = page.evaluate_handle("""() => {
            const headings = Array.from(document.querySelectorAll('h3,h4,[role="heading"]'));
            for (const h of headings) {
                if (h.textContent.toLowerCase().includes('skill')) {
                    let node = h;
                    for (let i = 0; i < 5; i++) {
                        node = node.parentElement;
                        if (!node) break;
                        const inp = node.querySelector('input');
                        if (inp && inp.offsetParent !== null) return inp;
                    }
                }
            }
            return null;
        }""")
        if not (skills_input and skills_input.as_element()):
            return
        skills_input = skills_input.as_element()

    logger.info("auto_apply: filling skills (%d items)", len(skills))
    for skill in skills[:30]:  # cap at 30 to avoid Workday limits
        try:
            skills_input.scroll_into_view_if_needed()
            # Use triple-click + type to properly replace React controlled input value
            skills_input.click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.wait_for_timeout(100)
            page.keyboard.type(skill)
            page.wait_for_timeout(800)

            # Pick the closest matching option (not just the first)
            opts = page.query_selector_all("[role='option']")
            if opts:
                opt_texts: list[tuple[str, object]] = []
                for opt in opts:
                    try:
                        t = opt.inner_text().strip()
                        if t and t.lower() != "no items.":
                            opt_texts.append((t, opt))
                    except Exception:
                        pass
                if opt_texts:
                    best = _closest_option(skill, [t for t, _ in opt_texts])
                    for text, opt in opt_texts:
                        if text == best:
                            opt.click()
                            break
                    else:
                        opt_texts[0][1].click()
                    page.wait_for_timeout(400)
            else:
                # No dropdown — skill may not exist in this ATS; skip
                page.keyboard.press("Escape")

            page.wait_for_timeout(200)
        except Exception as exc:
            logger.debug("auto_apply: skill fill failed for %r: %s", skill, exc)


def _fill_form(page, fields: list[dict], answers: dict[str, str], resume_path: str = "") -> None:
    for f in fields:
        ans = answers.get(f["label"])
        try:
            sel = f["selector"]
            if f["type"] in ("text", "email", "tel", "number", "textarea", "url", "search", "password"):
                if not ans:
                    continue
                el = page.query_selector(sel)
                if el:
                    el.fill(ans)
            elif f["type"] == "select":
                if not ans:
                    continue
                page.select_option(sel, label=_closest_option(ans, f["options"]))
            elif f["type"] == "workday_dropdown":
                if not ans:
                    continue
                _fill_workday_dropdown(page, f, ans)
                continue  # skip Tab press below
            elif f["type"] == "workday_date":
                _fill_workday_date_via_calendar(page, ans or "today", f.get("calendar_index", 0))
                continue  # calendar closes itself
            elif f["type"] == "file":
                path = f.get("resume_path") or resume_path
                if path:
                    try:
                        el = page.query_selector(sel)
                        if el:
                            el.set_input_files(path)
                            page.wait_for_timeout(1000)
                    except Exception as exc:
                        logger.warning("auto_apply: file upload failed for %r: %s", f["label"], exc)
                continue
            elif f["type"] == "radio":
                if not ans:
                    continue
                _click_radio(page, f["name"], ans, f["options"])
            elif f["type"] == "checkbox":
                if not ans:
                    continue
                el = page.query_selector(sel)
                if el and ans.lower() in ("yes", "true", "1") and not el.is_checked():
                    el.click()
            else:
                continue
            page.keyboard.press("Tab")
            page.wait_for_timeout(80)
        except Exception as exc:
            logger.warning("auto_apply: could not fill field %r: %s", f["label"], exc)


# ---------------------------------------------------------------------------
# HuggingFace LLM for unknown fields
# ---------------------------------------------------------------------------

_HF_SYSTEM = (
    "You are filling out a job application on behalf of a candidate. "
    "Use ONLY the profile and credentials provided — never invent anything. "
    "Return strict JSON where each key is the exact field label and the value is a short answer string. "
    "For select or radio fields, pick the closest matching option from the list provided. "
    "For email fields always use the provided email. For password fields always use the provided password. "
    "No markdown, no commentary, no explanation."
)

_HF_USER = """Candidate credentials (use exactly as provided):
  email: {email}
  password: {password}

Candidate profile:
{profile}

Applying for: {title} at {company}

Fields to answer (label → type [options if any]):
{fields_text}

Return JSON only: {{"field label": "answer", ...}}"""


def _llm_answers(profile: Profile, job: JobPosting, unknown_fields: list[dict]) -> dict[str, str]:
    if not unknown_fields or not settings.hf_api_token:
        return {}

    profile_json = {
        "headline": profile.headline,
        "years_experience": profile.years_experience,
        "skills": profile.skills,
        "preferred_titles": profile.preferred_titles,
        "work_authorized": "Yes, authorized to work in the US",
        "sponsorship_required": "No",
    }

    fields_text_lines = []
    for f in unknown_fields:
        line = f"- \"{f['label']}\" ({f['type']}"
        if f["options"]:
            line += f": {f['options']}"
        line += ")"
        fields_text_lines.append(line)

    user_msg = _HF_USER.format(
        email=settings.apply_email,
        password=settings.apply_password,
        profile=json.dumps(profile_json, indent=2),
        title=job.title,
        company=job.company,
        fields_text="\n".join(fields_text_lines),
    )

    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(
            model=settings.hf_model,
            token=settings.hf_api_token,
            provider=settings.hf_provider,
        )
        resp = client.chat_completion(
            messages=[
                {"role": "system", "content": _HF_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        return json.loads(content)
    except Exception as exc:
        logger.warning("auto_apply: HuggingFace call failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Multi-page form loop
# ---------------------------------------------------------------------------

_NEXT_BUTTON_TEXTS = [
    # Multi-step form navigation
    "next", "continue", "next step", "save and continue",
    "save & continue", "proceed", "next page", "next section",
    "continue with email", "submit",
]

# Auth-page-only button texts: only click these when inside <main>/<form>, never in <nav>/<header>
_AUTH_BUTTON_TEXTS = [
    "sign in", "signin", "log in", "login", "create account", "register",
]

_SUCCESS_PATTERNS = [
    "application submitted", "successfully submitted", "application received",
    "thank you for applying", "thanks for applying", "application complete",
    "we received your application", "your application has been",
    "successfully applied", "application was submitted",
]


_OTP_SELECTORS = (
    "input[autocomplete='one-time-code']",
    "input[name*='otp']",
    "input[name*='code']",
    "input[name*='verify']",
    "input[name*='token']",
)


def _resolve_answers(page, profile, job_posting, qa: dict, resume_path: str = "", resume_data: dict | None = None) -> dict[str, str]:
    fields = _extract_fields(page)
    logger.info("auto_apply: found %d fields on this page", len(fields))
    answers: dict[str, str] = {}

    # OTP field — fetch from Gmail before general mapping
    for sel in _OTP_SELECTORS:
        otp_el = page.query_selector(sel)
        if otp_el:
            logger.info("auto_apply: OTP field detected, fetching from Gmail")
            otp = _fetch_otp_from_gmail()
            if otp:
                try:
                    otp_el.fill(otp)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(2500)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8_000)
                    except Exception:
                        pass
                    logger.info("auto_apply: OTP submitted")
                except Exception as exc:
                    logger.warning("auto_apply: OTP fill failed: %s", exc)
            break

    for f in fields:
        low = f["label"].lower()
        for qa_key, qa_val in qa.items():
            if qa_key.lower() in low or low in qa_key.lower():
                answers[f["label"]] = str(qa_val)
                break

    for f in fields:
        if f["label"] in answers:
            continue
        factory = _match_field(f["label"])
        if factory:
            answers[f["label"]] = factory(profile)

    # Inject resume_path into file-upload field entries so _fill_form can use it
    for f in fields:
        if f["type"] == "file":
            f["resume_path"] = resume_path

    unknown = [f for f in fields if not answers.get(f["label"]) and f["type"] not in ("file", "workday_date")]
    if unknown:
        logger.info("auto_apply: calling HuggingFace for %d unknown fields", len(unknown))
        llm_ans = _llm_answers(profile, job_posting, unknown)
        answers.update(llm_ans)

    _fill_form(page, fields, answers, resume_path=resume_path)

    # After standard form fill, handle Workday structured sections
    if resume_data:
        _fill_workday_experience_section(page, resume_data.get("work_experience", []))
        _fill_workday_education_section(page)  # uses config values
        _fill_workday_skills_section(page, resume_data.get("skills", []))

    return answers


def _check_success(page) -> bool:
    """Return True if the current page shows a submission success message."""
    try:
        body = (page.locator("body").inner_text(timeout=3000) or "").lower()
        return any(pat in body for pat in _SUCCESS_PATTERNS)
    except Exception:
        return False


def _click_next(page) -> bool:
    """Click the Next/Continue button. Returns True if found and clicked."""
    def _try_click(loc, text: str) -> bool:
        try:
            if not loc.is_visible(timeout=800):
                return False
            logger.info("auto_apply: clicking next button: %r", text)
            loc.click()
            page.wait_for_timeout(2500)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            return True
        except Exception:
            return False

    for text in _NEXT_BUTTON_TEXTS:
        for tag in ("button", "a", "input"):
            if _try_click(page.locator(f"{tag}:has-text('{text}')").last, text):
                return True

    # Auth buttons: only click when inside <main> or <form> (not in nav/header)
    for text in _AUTH_BUTTON_TEXTS:
        for tag in ("button", "a"):
            loc = page.locator(f"main {tag}:has-text('{text}'), form {tag}:has-text('{text}')").last
            if _try_click(loc, text):
                return True

    return False


def _fill_and_advance(page, browser, profile, job_posting, qa: dict, resume_path: str = "", resume_data: dict | None = None) -> None:
    max_pages = 20
    for page_num in range(1, max_pages + 1):
        logger.info("auto_apply: processing form page %d", page_num)

        if _check_success(page):
            logger.info("auto_apply: SUCCESS — application submitted on page %d", page_num)
            return

        _resolve_answers(page, profile, job_posting, qa, resume_path=resume_path, resume_data=resume_data)

        # Check success again immediately after fill (some forms submit on last field)
        page.wait_for_timeout(500)
        if _check_success(page):
            logger.info("auto_apply: SUCCESS — application submitted after filling page %d", page_num)
            return

        # Try to advance to next page
        advanced = _click_next(page)
        if not advanced:
            logger.info("auto_apply: no Next button found on page %d — leaving browser open for user", page_num)
            break

    # Keep browser open so user can review / submit manually
    logger.info("auto_apply: browser left open for user review and final submit")
    while True:
        try:
            page.wait_for_timeout(5000)
            if not browser.is_connected():
                break
            if _check_success(page):
                logger.info("auto_apply: user submitted — success detected, browser can be closed")
                page.wait_for_timeout(5000)
                break
        except Exception:
            break


# ---------------------------------------------------------------------------
# Main runner (executes in a daemon thread)
# ---------------------------------------------------------------------------

def _run(draft_id: str) -> None:
    from playwright.sync_api import sync_playwright

    with SessionLocal() as db:
        draft = db.get(ApplicationDraft, draft_id)
        if not draft:
            logger.error("auto_apply: draft %s not found", draft_id)
            return

        profile = db.get(Profile, draft.profile_id)
        saved_job = db.get(SavedJob, draft.saved_job_id)
        job_posting = db.get(JobPosting, draft.job_id)

        if not (profile and saved_job and job_posting):
            logger.error("auto_apply: missing profile/saved_job/job_posting for draft %s", draft_id)
            return

        job_url = job_posting.url
        qa = (draft.qa_answers_json or {}) if isinstance(draft.qa_answers_json, dict) else {}

        # Fetch tailored resume PDF for file upload steps
        resume_pdf_bytes: bytes | None = None
        resume_data: dict | None = None
        tailored = (
            db.query(TailoredResume)
            .filter(TailoredResume.saved_job_id == draft.saved_job_id)
            .order_by(TailoredResume.version.desc())
            .first()
        )
        if tailored and tailored.pdf_bytes:
            resume_pdf_bytes = tailored.pdf_bytes
            logger.info("auto_apply: loaded tailored resume PDF (%d bytes)", len(resume_pdf_bytes))
            if tailored.latex_source:
                resume_data = _parse_latex_resume(tailored.latex_source)
        else:
            logger.info("auto_apply: no tailored resume PDF found, will skip file uploads")

    logger.info("auto_apply: launching browser for %s", job_url)

    # Write resume PDF to a temp file named HarshBhaskar_{job_title}.pdf
    resume_path = ""
    tmp_file = None
    if resume_pdf_bytes:
        safe_title = re.sub(r'[^\w\-]', '_', job_posting.title or "Resume")[:60]
        resume_filename = f"HarshBhaskar_{safe_title}.pdf"
        tmp_dir = tempfile.mkdtemp(prefix="autoapply_")
        resume_path = str(Path(tmp_dir) / resume_filename)
        with open(resume_path, "wb") as _f:
            _f.write(resume_pdf_bytes)
        logger.info("auto_apply: resume temp file: %s", resume_path)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
            page = browser.new_page(viewport=None)

            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
                # Wait for JS to render (SPAs like Workday need this)
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)

                # Click the Apply button on the listing page to reach the application form
                clicked = _click_apply_button(page)
                if clicked:
                    try:
                        page.wait_for_load_state("networkidle", timeout=10_000)
                    except Exception:
                        pass
                    page.wait_for_timeout(3000)
                    # Some ATSes open a new tab — switch to it
                    all_pages = page.context.pages
                    if len(all_pages) > 1:
                        page = all_pages[-1]
                        try:
                            page.wait_for_load_state("networkidle", timeout=10_000)
                        except Exception:
                            pass
                        page.wait_for_timeout(2000)
                else:
                    logger.info("auto_apply: no Apply button found — treating page as the form itself")

                # Multi-page form loop handles everything: login, OTP, form pages
                _fill_and_advance(page, browser, profile, job_posting, qa, resume_path=resume_path, resume_data=resume_data)

            except Exception as exc:
                logger.error("auto_apply: error during apply: %s", exc, exc_info=True)
    finally:
        # Clean up temp resume dir
        if resume_path:
            try:
                import shutil as _shutil
                _shutil.rmtree(Path(resume_path).parent, ignore_errors=True)
            except Exception:
                pass


def trigger_apply(draft_id: str) -> None:
    import subprocess
    script = Path(__file__).parent.parent.parent / "run_auto_apply.py"
    proc = subprocess.Popen(
        [sys.executable, str(script), draft_id],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    logger.info("auto_apply: launched subprocess PID %s for draft %s", proc.pid, draft_id)
