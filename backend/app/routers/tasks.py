from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FetchRun, FetchRunTarget
from app.schemas import FetchRunStatusResponse, FetchRunTargetStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{fetch_run_id}", response_model=FetchRunStatusResponse)
def get_fetch_run_status(
    fetch_run_id: str, db: Session = Depends(get_db)
) -> FetchRunStatusResponse:
    run = db.get(FetchRun, fetch_run_id)
    if not run:
        raise HTTPException(404, f"Fetch run {fetch_run_id!r} not found")

    run_targets = (
        db.query(FetchRunTarget)
        .filter(FetchRunTarget.fetch_run_id == fetch_run_id)
        .all()
    )

    return FetchRunStatusResponse(
        fetch_run_id=run.id,
        profile_id=run.profile_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_jobs_fetched=run.total_jobs_fetched,
        total_jobs_normalized=run.total_jobs_normalized,
        total_jobs_matched=run.total_jobs_matched,
        error_summary=run.error_summary,
        targets=[
            FetchRunTargetStatus(
                target_id=t.source_target_id,
                status=t.status,
                jobs_fetched=t.jobs_fetched,
                error_message=t.error_message,
            )
            for t in run_targets
        ],
    )
