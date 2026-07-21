"""Application Drafting layer.

Generates a job-specific application package (fit summary, keyword-gap diff,
tailored resume JSON, Q&A skeleton) and persists it as an ApplicationDraft.

Provider-pluggable: DeterministicProvider runs offline by default;
HuggingFaceProvider enriches prose-heavy fields via the HF Inference Providers API.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models import ApplicationDraft, JobMatch, JobPosting, Profile, SavedJob

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic facts (computed before any provider call)
# ---------------------------------------------------------------------------


def _normalize(values: list[str] | None) -> list[str]:
    return [v.strip().lower() for v in (values or []) if v and v.strip()]


def _keyword_gap(profile_skills: list[str] | None, job_tags: list[str] | None) -> dict:
    profile_set = set(_normalize(profile_skills))
    job_set = set(_normalize(job_tags))
    matched = sorted(profile_set & job_set)
    missing = sorted(job_set - profile_set)
    return {"matched": matched, "missing": missing}


def _confidence_from_match(match: JobMatch | None, gap: dict) -> float:
    if match is not None:
        return round(float(match.overall_score), 4)
    matched = len(gap.get("matched", []))
    total = matched + len(gap.get("missing", []))
    return round(matched / total, 4) if total else 0.0


def _deterministic_qa(profile: Profile) -> dict:
    titles = profile.preferred_titles or []
    levels = profile.preferred_level or []
    return {
        "work_authorization": "Authorized to work in the United States.",
        "sponsorship": "No sponsorship required.",
        "location": "Open to roles in the United States and remote.",
        "preferred_titles": titles,
        "preferred_levels": levels,
        "years_experience": profile.years_experience,
        "why_this_role": None,
        "why_this_company": None,
        "salary_expectations": None,
    }


def _structured_resume(profile: Profile) -> dict:
    return {
        "headline": profile.headline,
        "years_experience": profile.years_experience,
        "skills": profile.skills or [],
        "preferred_titles": profile.preferred_titles or [],
        "preferred_levels": profile.preferred_level or [],
    }


def _compute_facts(
    profile: Profile, job_posting: JobPosting, match: JobMatch | None
) -> dict:
    gap = _keyword_gap(profile.skills, job_posting.tags)
    return {
        "company": job_posting.company,
        "title": job_posting.title,
        "location": job_posting.location,
        "matched_skills": gap["matched"],
        "missing_skills": gap["missing"],
        "keyword_gap_summary": gap,
        "match_overall": match.overall_score if match else None,
        "match_title": match.title_score if match else None,
        "match_skills": match.skills_score if match else None,
        "match_level": match.level_score if match else None,
        "structured_resume": _structured_resume(profile),
        "deterministic_qa": _deterministic_qa(profile),
        "confidence_score": _confidence_from_match(match, gap),
    }


# ---------------------------------------------------------------------------
# Provider interface + DeterministicProvider
# ---------------------------------------------------------------------------


class DraftingProvider(Protocol):
    name: str

    def generate(
        self,
        profile: Profile,
        saved_job: SavedJob,
        job_posting: JobPosting,
        deterministic_facts: dict,
    ) -> dict: ...


class DeterministicProvider:
    name = "deterministic"

    def generate(
        self,
        profile: Profile,
        saved_job: SavedJob,
        job_posting: JobPosting,
        deterministic_facts: dict,
    ) -> dict:
        matched = deterministic_facts["matched_skills"]
        missing = deterministic_facts["missing_skills"]
        title = deterministic_facts["title"]
        company = deterministic_facts["company"]
        overall = deterministic_facts.get("match_overall")

        score_pct = f"{round((overall or 0) * 100)}%" if overall is not None else "n/a"
        matched_str = ", ".join(matched[:8]) if matched else "limited overlap"
        missing_str = ", ".join(missing[:6]) if missing else "no major gaps"

        fit_summary = (
            f"Match score {score_pct} for {title} at {company}. "
            f"Strong skill overlap on {matched_str}. "
            f"Notable gaps: {missing_str}."
        )

        return {
            "fit_summary": fit_summary,
            "keyword_gap_summary": deterministic_facts["keyword_gap_summary"],
            "tailored_resume_json": deterministic_facts["structured_resume"],
            "qa_answers_json": deterministic_facts["deterministic_qa"],
            "confidence_score": deterministic_facts["confidence_score"],
        }


# ---------------------------------------------------------------------------
# HuggingFaceProvider
# ---------------------------------------------------------------------------


_HF_SYSTEM_PROMPT = (
    "You are an application-drafting assistant for a job seeker. "
    "Use ONLY the deterministic facts the user supplies. "
    "Never invent skills, employers, or experiences. "
    "Return STRICT JSON matching the requested schema. "
    "No markdown fences, no commentary, no leading or trailing text."
)


_HF_USER_TEMPLATE = """Generate a tailored application package for this candidate and job.

DETERMINISTIC FACTS (do not contradict):
{facts}

REQUIRED OUTPUT (strict JSON, no other text):
{{
  "fit_summary": "<2-3 sentence prose summary explaining why this candidate is a fit, grounded in matched_skills and match scores. Mention notable gaps from missing_skills.>",
  "qa_free_text": {{
    "why_this_role": "<2-3 sentences using only matched_skills as evidence>",
    "why_this_company": "<2 sentences; if no signal, return null>",
    "salary_expectations": null
  }}
}}"""


class HuggingFaceProvider:
    name = "huggingface"

    def __init__(
        self,
        token: str,
        model: str,
        provider: str,
    ) -> None:
        self._token = token
        self._model = model
        self._provider = provider
        self._client = None  # lazy

    def _get_client(self):
        if self._client is None:
            from huggingface_hub import InferenceClient

            self._client = InferenceClient(
                model=self._model,
                token=self._token,
                provider=self._provider,
            )
        return self._client

    def _call(self, deterministic_facts: dict) -> dict | None:
        facts_subset = {
            k: deterministic_facts[k]
            for k in (
                "company",
                "title",
                "location",
                "matched_skills",
                "missing_skills",
                "match_overall",
            )
            if k in deterministic_facts
        }
        user = _HF_USER_TEMPLATE.format(facts=json.dumps(facts_subset, indent=2))

        client = self._get_client()
        try:
            resp = client.chat_completion(
                messages=[
                    {"role": "system", "content": _HF_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                max_tokens=600,
                temperature=0.3,
            )
            content = resp.choices[0].message.content if resp.choices else ""
        except Exception as exc:  # network/auth/etc
            logger.warning("HuggingFaceProvider call failed: %s", exc)
            return None

        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("HuggingFaceProvider returned non-JSON content: %r", content[:200])
            return None

    def generate(
        self,
        profile: Profile,
        saved_job: SavedJob,
        job_posting: JobPosting,
        deterministic_facts: dict,
    ) -> dict:
        # Always start from the deterministic baseline so missing fields stay populated.
        baseline = DeterministicProvider().generate(
            profile, saved_job, job_posting, deterministic_facts
        )

        # Two-attempt JSON parse before falling back.
        llm = self._call(deterministic_facts) or self._call(deterministic_facts)
        if llm is None:
            logger.info("HuggingFaceProvider falling back to deterministic baseline")
            return baseline

        fit_summary = llm.get("fit_summary") or baseline["fit_summary"]
        qa_free = llm.get("qa_free_text") or {}
        qa_merged = dict(baseline["qa_answers_json"])
        for key in ("why_this_role", "why_this_company", "salary_expectations"):
            if qa_free.get(key):
                qa_merged[key] = qa_free[key]

        return {
            "fit_summary": fit_summary,
            "keyword_gap_summary": baseline["keyword_gap_summary"],
            "tailored_resume_json": baseline["tailored_resume_json"],
            "qa_answers_json": qa_merged,
            "confidence_score": baseline["confidence_score"],
        }


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def _select_provider() -> DraftingProvider:
    choice = (settings.drafting_provider or "deterministic").lower()
    if choice == "huggingface":
        if not settings.hf_api_token:
            logger.warning(
                "DRAFTING_PROVIDER=huggingface but HF_API_TOKEN is unset; "
                "falling back to DeterministicProvider"
            )
            return DeterministicProvider()
        return HuggingFaceProvider(
            token=settings.hf_api_token,
            model=settings.hf_model,
            provider=settings.hf_provider,
        )
    return DeterministicProvider()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_draft(
    db: Session,
    *,
    profile: Profile,
    saved_job: SavedJob,
    job_posting: JobPosting,
) -> ApplicationDraft:
    """Create or regenerate an ApplicationDraft for a (profile, saved_job)."""
    match = (
        db.query(JobMatch)
        .filter(
            JobMatch.profile_id == profile.id,
            JobMatch.job_id == job_posting.id,
        )
        .order_by(JobMatch.created_at.desc())
        .first()
    )
    facts = _compute_facts(profile, job_posting, match)
    provider = _select_provider()

    try:
        result = provider.generate(profile, saved_job, job_posting, facts)
    except Exception as exc:
        logger.exception("Provider %s failed; falling back to deterministic", provider.name)
        result = DeterministicProvider().generate(profile, saved_job, job_posting, facts)
        result["_provider_error"] = str(exc)

    existing = (
        db.query(ApplicationDraft)
        .filter(
            ApplicationDraft.profile_id == profile.id,
            ApplicationDraft.saved_job_id == saved_job.id,
        )
        .first()
    )

    if existing is None:
        draft = ApplicationDraft(
            profile_id=profile.id,
            saved_job_id=saved_job.id,
            job_id=job_posting.id,
            status="review_pending",
            fit_summary=result.get("fit_summary"),
            keyword_gap_summary=result.get("keyword_gap_summary"),
            tailored_resume_json=result.get("tailored_resume_json"),
            tailored_resume_version=1,
            qa_answers_json=result.get("qa_answers_json"),
            confidence_score=float(result.get("confidence_score") or 0.0),
            intent_snapshot_json={"provider": provider.name},
        )
        db.add(draft)
    else:
        existing.status = "review_pending"
        existing.fit_summary = result.get("fit_summary")
        existing.keyword_gap_summary = result.get("keyword_gap_summary")
        existing.tailored_resume_json = result.get("tailored_resume_json")
        existing.tailored_resume_version = (existing.tailored_resume_version or 0) + 1
        existing.qa_answers_json = result.get("qa_answers_json")
        existing.confidence_score = float(result.get("confidence_score") or 0.0)
        existing.intent_snapshot_json = {"provider": provider.name}
        existing.approved_at = None
        draft = existing

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        draft = (
            db.query(ApplicationDraft)
            .filter(
                ApplicationDraft.profile_id == profile.id,
                ApplicationDraft.saved_job_id == saved_job.id,
            )
            .first()
        )
        if draft is None:
            raise
        return draft

    db.refresh(draft)
    return draft


def mark_stale_for_profile(db: Session, profile_id: str, *, reason: str | None = None) -> int:
    """Flip drafts in ('review_pending', 'approved') to 'stale' for one profile.

    Returns the number of rows updated. Called from profiles router on PATCH/POST.
    """
    drafts = (
        db.query(ApplicationDraft)
        .filter(
            ApplicationDraft.profile_id == profile_id,
            ApplicationDraft.status.in_(("review_pending", "approved")),
        )
        .all()
    )
    count = 0
    for d in drafts:
        d.status = "stale"
        snapshot = d.intent_snapshot_json or {}
        snapshot["stale_reason"] = reason or "profile_updated"
        snapshot["stale_at"] = datetime.now(timezone.utc).isoformat()
        d.intent_snapshot_json = snapshot
        count += 1
    if count:
        db.commit()
    return count
