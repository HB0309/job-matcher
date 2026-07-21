import logging
import re

from app.models import Profile
from app.workers.normalizer import NormalizedJob

log = logging.getLogger(__name__)

_LEVEL_ORDER = ["new_grad", "entry", "junior", "mid", "senior", "staff", "principal"]

# Job-function keywords that indicate a non-technical role
_NON_TECH_TITLE_WORDS = {
    "sales", "marketing", "recruiter", "recruiting", "talent acquisition",
    "account executive", "account manager", "business development",
    "customer success", "customer support", "customer service",
    "finance", "accounting", "controller", "legal", "counsel",
    "operations manager", "office manager", "executive assistant",
    "product marketing", "demand generation", "growth marketing",
    "partnerships", "revenue", "inside sales", "field sales",
    "sales development", "sales engineer",
}

# Generic words stripped before extracting domain keywords from preferred titles
_TITLE_GENERIC_WORDS = {
    "engineer", "developer", "specialist", "associate", "manager", "director",
    "lead", "senior", "junior", "staff", "principal", "head", "officer",
    "new", "grad", "graduate", "entry", "level", "ii", "iii", "iv", "i",
    "jr", "sr", "mid", "the", "a", "an", "and", "or", "of", "in", "at",
    "remote", "hybrid", "onsite", "contract", "intern", "internship",
}


def extract_domain_keywords(preferred_titles: list[str]) -> set[str]:
    """Extract meaningful domain keywords from preferred titles (e.g. 'security', 'soc', 'analyst')."""
    keywords: set[str] = set()
    for title in preferred_titles:
        for word in title.lower().split():
            word = re.sub(r"[^a-z]", "", word)
            if word and len(word) > 2 and word not in _TITLE_GENERIC_WORDS:
                keywords.add(word)
    return keywords


def passes_title_filter(job_title: str, domain_keywords: set[str]) -> bool:
    """Return True if the job title contains at least one domain keyword (whole-word match).
    If no domain keywords were extracted, all jobs pass."""
    if not domain_keywords:
        return True
    job_lower = job_title.lower()
    return any(re.search(r"\b" + re.escape(kw) + r"\b", job_lower) for kw in domain_keywords)


def _all_words_present(preferred: str, job_title: str) -> bool:
    """Return True only if every word of preferred appears as a whole word in job_title."""
    job_lower = job_title.lower()
    for word in preferred.lower().split():
        if not re.search(r"\b" + re.escape(word) + r"\b", job_lower):
            return False
    return True


def _title_score(preferred_titles: list[str], job_title: str) -> float:
    if not preferred_titles:
        return 0.5
    job_lower = job_title.lower()
    best = 0.0
    for title in preferred_titles:
        if _all_words_present(title, job_title):
            return 1.0
        overlap = len(set(title.lower().split()) & set(job_lower.split())) / max(len(title.lower().split()), 1)
        best = max(best, overlap)
    return best


def is_domain_mismatch(job_title: str, preferred_titles: list[str]) -> bool:
    """Return True if the job is clearly a non-technical role with no overlap with preferred titles."""
    job_lower = job_title.lower()
    if not any(kw in job_lower for kw in _NON_TECH_TITLE_WORDS):
        return False
    for title in preferred_titles:
        for word in title.lower().split():
            if len(word) > 3 and re.search(r"\b" + re.escape(word) + r"\b", job_lower):
                return False
    return True


def _skills_score(profile_skills: list[str], job_tags: list[str]) -> float:
    if not profile_skills or not job_tags:
        return 0.0
    profile_set = {s.lower() for s in profile_skills}
    job_set = {t.lower() for t in job_tags}
    return min(len(profile_set & job_set) / max(len(profile_set), 1), 1.0)


def _level_score(preferred_levels: list[str] | None, normalized_level: str | None) -> float:
    if not preferred_levels or not normalized_level:
        return 0.5
    best = 0.0
    for preferred_level in preferred_levels:
        if preferred_level == normalized_level:
            return 1.0
        try:
            distance = abs(_LEVEL_ORDER.index(preferred_level) - _LEVEL_ORDER.index(normalized_level))
            # Steeper penalty: 0.5 per step (vs 0.3 before), floor at 0
            best = max(best, max(0.0, 1.0 - distance * 0.5))
        except ValueError:
            best = max(best, 0.5)
    return best


def _location_score(location: str | None) -> float:
    if not location:
        return 0.5
    loc = location.lower()
    if "remote" in loc:
        return 1.0
    if any(kw in loc for kw in ["united states", "usa", " us,", "america"]):
        return 0.8
    return 0.3


def passes_level_filter(job_level: str | None, preferred_levels: list[str]) -> bool:
    """Return False only when a job's level is 2+ steps from all preferred levels."""
    if not preferred_levels:
        return True
    if not job_level or job_level not in _LEVEL_ORDER:
        return True
    job_idx = _LEVEL_ORDER.index(job_level)
    for pref in preferred_levels:
        if pref in _LEVEL_ORDER:
            if abs(_LEVEL_ORDER.index(pref) - job_idx) <= 1:
                return True
    return False


def score_job(profile: Profile, job: NormalizedJob) -> dict[str, float]:
    t = _title_score(profile.preferred_titles or [], job.title)  # stored for reference, not weighted
    s = _skills_score(profile.skills or [], job.tags)
    l = _level_score(profile.preferred_level or [], job.normalized_level)
    loc = _location_score(job.location)
    # weights: skills 35%, level 50%, location 15%
    # Title is pre-filtered upstream — any job reaching here already matched the domain
    overall = round(0.35 * s + 0.50 * l + 0.15 * loc, 4)
    return {"overall": overall, "title": round(t, 4), "skills": round(s, 4), "level": round(l, 4), "location": round(loc, 4)}


def score_jobs(profile: Profile, jobs: list[NormalizedJob]) -> list[dict[str, float]]:
    return [score_job(profile, job) for job in jobs]
