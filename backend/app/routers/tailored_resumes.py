import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import JobPosting, Profile, SavedJob, TailoredResume
from app.schemas import TailoredResumeCreate, TailoredResumeResponse
from app.workers.resume_tailor import tailor_resume

router = APIRouter(tags=["tailored-resumes"], dependencies=[Depends(get_current_user)])
# Separate router for the PDF download — auth is handled inside the endpoint
# so browsers can open the URL directly without an Authorization header.
pdf_router = APIRouter(tags=["tailored-resumes"])


def _to_response(r: TailoredResume) -> TailoredResumeResponse:
    return TailoredResumeResponse(
        id=r.id,
        profile_id=r.profile_id,
        job_id=r.job_id,
        saved_job_id=r.saved_job_id,
        user_notes=r.user_notes,
        tailoring_rationale=(r.gemini_analysis or {}).get("tailoring_rationale"),
        has_pdf=r.pdf_bytes is not None,
        version=r.version,
        created_at=r.created_at,
    )


@router.post("/tailored-resumes", response_model=TailoredResumeResponse)
def create_tailored_resume(body: TailoredResumeCreate, db: Session = Depends(get_db)):
    profile = db.get(Profile, body.profile_id)
    if not profile:
        raise HTTPException(404, f"Profile {body.profile_id!r} not found")

    saved = db.get(SavedJob, body.saved_job_id)
    if not saved:
        raise HTTPException(404, f"Saved job {body.saved_job_id!r} not found")
    if saved.profile_id != body.profile_id:
        raise HTTPException(400, "Saved job does not belong to this profile")

    job_posting = db.get(JobPosting, saved.job_id)
    if not job_posting:
        raise HTTPException(404, "Job posting not found")

    try:
        record = tailor_resume(
            db,
            profile=profile,
            saved_job=saved,
            job_posting=job_posting,
            user_notes=body.user_notes,
        )
    except Exception as exc:
        raise HTTPException(500, f"Resume tailoring failed: {exc}") from exc

    return _to_response(record)


@router.get("/tailored-resumes", response_model=TailoredResumeResponse)
def lookup_tailored_resume(
    profile_id: str = Query(...),
    saved_job_id: str = Query(...),
    db: Session = Depends(get_db),
):
    record = (
        db.query(TailoredResume)
        .filter(
            TailoredResume.profile_id == profile_id,
            TailoredResume.saved_job_id == saved_job_id,
        )
        .order_by(TailoredResume.created_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(404, "No tailored resume for this job")
    return _to_response(record)


@pdf_router.get("/tailored-resumes/{resume_id}/pdf")
def download_pdf(
    resume_id: str,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    # Accept token as query param so browsers can open the URL directly
    if not token:
        raise HTTPException(401, "Not authenticated")
    from jose import JWTError
    from app.workers.auth import decode_token
    try:
        decode_token(token)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    record = db.get(TailoredResume, resume_id)
    if not record:
        raise HTTPException(404, "Tailored resume not found")
    if not record.pdf_bytes:
        raise HTTPException(404, "PDF not available — compilation may have failed")

    # Build filename: HarshBhaskar_{job_title}.pdf
    job_title = ""
    saved = db.get(SavedJob, record.saved_job_id) if record.saved_job_id else None
    if saved:
        posting = db.get(JobPosting, saved.job_id)
        if posting and posting.title:
            job_title = re.sub(r"[^\w\-]", "_", posting.title)[:60]
    filename = f"HarshBhaskar_{job_title}.pdf" if job_title else f"HarshBhaskar_Resume_v{record.version}.pdf"

    return Response(
        content=record.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

