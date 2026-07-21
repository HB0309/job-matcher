from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    application_drafts,
    auth,
    intent,
    jobs,
    profiles,
    saved_jobs,
    schedules,
    sources,
    tailored_resumes,
    tasks,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db import SessionLocal
    from app.models import ScheduledFetch
    from app.workers.scheduler import scheduler, register

    with SessionLocal() as db:
        for sf in db.query(ScheduledFetch).filter_by(enabled=True).all():
            register(sf)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Job Matcher API",
    description="ATS-first job aggregation and matching — v1",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(jobs.router)
app.include_router(sources.router)
app.include_router(tasks.router)
app.include_router(saved_jobs.router)
app.include_router(schedules.router)
app.include_router(application_drafts.router)
app.include_router(intent.router)
app.include_router(tailored_resumes.router)
app.include_router(tailored_resumes.pdf_router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    return {"status": "ok"}

