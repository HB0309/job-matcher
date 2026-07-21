from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler(timezone="UTC")


def _run_fetch(schedule_id: str) -> None:
    from app.db import SessionLocal
    from app.models import ScheduledFetch
    from app.workers.orchestrator import run_fetch_and_match

    with SessionLocal() as db:
        sf = db.get(ScheduledFetch, schedule_id)
        if sf is None or not sf.enabled:
            return
        try:
            run_fetch_and_match(db, sf.profile_id, connectors=sf.connectors or None)
        except Exception:
            pass
        sf.last_run_at = datetime.now(timezone.utc)
        sf.next_run_at = datetime.now(timezone.utc) + timedelta(hours=sf.interval_hours)
        db.commit()


def register(schedule) -> None:
    scheduler.add_job(
        _run_fetch,
        trigger=IntervalTrigger(hours=schedule.interval_hours),
        id=schedule.id,
        args=[schedule.id],
        replace_existing=True,
        next_run_time=schedule.next_run_at or (
            datetime.now(timezone.utc) + timedelta(hours=schedule.interval_hours)
        ),
    )


def unregister(schedule_id: str) -> None:
    if scheduler.get_job(schedule_id):
        scheduler.remove_job(schedule_id)
