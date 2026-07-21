from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Connector, JobPosting, Profile, SavedJob
from app.schemas import SavedJobCreate, SavedJobResponse, SavedJobUpdate, SavedJobWithDetails

router = APIRouter(tags=["saved-jobs"], dependencies=[Depends(get_current_user)])


def _to_details(saved: SavedJob, jp: JobPosting, profile: Profile, conn: Connector) -> SavedJobWithDetails:
    return SavedJobWithDetails(
        id=saved.id,
        profile_id=saved.profile_id,
        profile_headline=profile.headline,
        job_id=saved.job_id,
        title=jp.title,
        company=jp.company,
        url=jp.url,
        location=jp.location,
        connector_name=conn.name,
        status=saved.status,
        saved_at=saved.saved_at,
        applied_at=saved.applied_at,
    )


@router.get("/saved-jobs", response_model=list[SavedJobWithDetails])
def list_saved_jobs(profile_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    q = (
        db.query(SavedJob, JobPosting, Profile, Connector)
        .join(JobPosting, SavedJob.job_id == JobPosting.id)
        .join(Profile, SavedJob.profile_id == Profile.id)
        .join(Connector, JobPosting.connector_id == Connector.id)
    )
    if profile_id:
        q = q.filter(SavedJob.profile_id == profile_id)
    rows = q.order_by(SavedJob.saved_at.desc()).all()
    return [_to_details(saved, jp, profile, conn) for saved, jp, profile, conn in rows]


@router.post("/saved-jobs", response_model=SavedJobResponse, status_code=201)
def save_job(body: SavedJobCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(SavedJob)
        .filter(SavedJob.profile_id == body.profile_id, SavedJob.job_id == body.job_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Job already saved")
    record = SavedJob(profile_id=body.profile_id, job_id=body.job_id, status="saved")
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/saved-jobs/{saved_job_id}", response_model=SavedJobResponse)
def update_saved_job(saved_job_id: str, body: SavedJobUpdate, db: Session = Depends(get_db)):
    record = db.query(SavedJob).filter(SavedJob.id == saved_job_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Saved job not found")
    record.status = body.status
    if body.status == "applied" and record.applied_at is None:
        record.applied_at = datetime.now(timezone.utc)
    elif body.status == "saved":
        record.applied_at = None
    db.commit()
    db.refresh(record)
    return record


@router.delete("/saved-jobs/{saved_job_id}", status_code=204)
def delete_saved_job(saved_job_id: str, db: Session = Depends(get_db)):
    record = db.query(SavedJob).filter(SavedJob.id == saved_job_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Saved job not found")
    db.delete(record)
    db.commit()
