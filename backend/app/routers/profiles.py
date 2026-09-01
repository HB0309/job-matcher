import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_current_user
from app.models import Profile, User
from app.schemas import ProfileResponse, ProfileUpdateRequest
from app.workers.resume_parser import extract_text, parse_resume, parse_resume_llm

router = APIRouter(tags=["profiles"])


def _profile_to_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse(
        profile_id=profile.id,
        headline=profile.headline,
        years_experience=profile.years_experience,
        skills=profile.skills or [],
        preferred_titles=profile.preferred_titles or [],
        preferred_level=profile.preferred_level or [],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("/profiles", response_model=list[ProfileResponse])
def list_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProfileResponse]:
    user = current_user
    profiles = (
        db.query(Profile)
        .filter(Profile.user_id == user.id)
        .order_by(Profile.created_at.desc())
        .all()
    )
    return [_profile_to_response(p) for p in profiles]


@router.post("/profiles", response_model=ProfileResponse, status_code=200)
def create_profile(
    resume: UploadFile = File(...),
    preferred_titles: str = Form(...),
    preferred_level: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    if not resume.filename or not resume.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(400, "Resume must be a .pdf or .docx file")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(resume.filename).suffix.lower()
    save_path = upload_dir / f"{uuid.uuid4()}{suffix}"

    try:
        with save_path.open("wb") as f:
            shutil.copyfileobj(resume.file, f)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save resume: {exc}") from exc

    titles_list = [t.strip() for t in preferred_titles.split(",") if t.strip()]
    levels_list = [l.strip() for l in preferred_level.split(",") if l.strip()]

    try:
        parsed = parse_resume(str(save_path), preferred_titles=titles_list)
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Resume parsing failed: {exc}") from exc

    # Best-effort LLM enrichment (Stage 0 of agentic matching) — runs once per
    # upload, never blocks profile creation if it fails (see parse_resume_llm docstring).
    parsed_experience: dict | None = None
    try:
        parsed_experience = parse_resume_llm(extract_text(str(save_path)))
    except Exception:
        parsed_experience = None

    profile = Profile(
        user_id=current_user.id,
        raw_resume_path=str(save_path),
        headline=parsed.headline,
        years_experience=parsed.years_experience,
        skills=parsed.skills,
        preferred_titles=titles_list,
        preferred_level=levels_list,
        parsed_experience=parsed_experience,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _profile_to_response(profile)


@router.patch("/profiles/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: str,
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    from app.workers.application_drafter import mark_stale_for_profile

    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, f"Profile {profile_id!r} not found")

    titles_changed = (
        body.preferred_titles is not None
        and body.preferred_titles != (profile.preferred_titles or [])
    )
    levels_changed = (
        body.preferred_level is not None
        and body.preferred_level != (profile.preferred_level or [])
    )

    if body.preferred_titles is not None:
        profile.preferred_titles = body.preferred_titles
    if body.preferred_level is not None:
        profile.preferred_level = body.preferred_level
    db.commit()
    db.refresh(profile)

    if titles_changed or levels_changed:
        reason = "titles_changed" if titles_changed else "level_changed"
        mark_stale_for_profile(db, profile_id, reason=reason)

    return _profile_to_response(profile)


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, f"Profile {profile_id!r} not found")
    return _profile_to_response(profile)


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    from app.models import FetchRun, FetchRunTarget, JobMatch

    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, f"Profile {profile_id!r} not found")

    # Delete in FK order: matches → run_targets → runs → profile
    run_ids = [r.id for r in db.query(FetchRun.id).filter(FetchRun.profile_id == profile_id)]
    if run_ids:
        db.query(FetchRunTarget).filter(FetchRunTarget.fetch_run_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(JobMatch).filter(JobMatch.profile_id == profile_id).delete(synchronize_session=False)
    db.query(FetchRun).filter(FetchRun.profile_id == profile_id).delete(synchronize_session=False)

    resume_path = profile.raw_resume_path
    db.delete(profile)
    db.commit()

    if resume_path:
        Path(resume_path).unlink(missing_ok=True)
