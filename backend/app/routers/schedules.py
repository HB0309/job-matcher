from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import ScheduledFetch
from app.schemas import ScheduledFetchCreate, ScheduledFetchResponse, ScheduledFetchUpdate
from app.workers.scheduler import register, unregister

router = APIRouter(tags=["schedules"], dependencies=[Depends(get_current_user)])


@router.get("/schedules", response_model=list[ScheduledFetchResponse])
def list_schedules(profile_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    q = db.query(ScheduledFetch)
    if profile_id:
        q = q.filter(ScheduledFetch.profile_id == profile_id)
    return q.order_by(ScheduledFetch.created_at.desc()).all()


@router.post("/schedules", response_model=ScheduledFetchResponse, status_code=201)
def create_schedule(body: ScheduledFetchCreate, db: Session = Depends(get_db)):
    sf = ScheduledFetch(
        profile_id=body.profile_id,
        connectors=body.connectors,
        interval_hours=body.interval_hours,
        enabled=True,
        next_run_at=datetime.now(timezone.utc) + timedelta(hours=body.interval_hours),
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)
    register(sf)
    return sf


@router.patch("/schedules/{schedule_id}", response_model=ScheduledFetchResponse)
def update_schedule(schedule_id: str, body: ScheduledFetchUpdate, db: Session = Depends(get_db)):
    sf = db.get(ScheduledFetch, schedule_id)
    if not sf:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.connectors is not None:
        sf.connectors = body.connectors
    if body.interval_hours is not None:
        sf.interval_hours = body.interval_hours
        sf.next_run_at = datetime.now(timezone.utc) + timedelta(hours=sf.interval_hours)
    if body.enabled is not None:
        sf.enabled = body.enabled

    db.commit()
    db.refresh(sf)

    if sf.enabled:
        register(sf)
    else:
        unregister(sf.id)

    return sf


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)):
    sf = db.get(ScheduledFetch, schedule_id)
    if not sf:
        raise HTTPException(status_code=404, detail="Schedule not found")
    unregister(sf.id)
    db.delete(sf)
    db.commit()
