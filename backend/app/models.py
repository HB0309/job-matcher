import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    profiles: Mapped[list["Profile"]] = relationship("Profile", back_populates="user")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    raw_resume_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_titles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_level: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="profiles")
    fetch_runs: Mapped[list["FetchRun"]] = relationship("FetchRun", back_populates="profile")
    job_matches: Mapped[list["JobMatch"]] = relationship("JobMatch", back_populates="profile")


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(50), server_default="public", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_targets: Mapped[list["SourceTarget"]] = relationship("SourceTarget", back_populates="connector")
    job_postings: Mapped[list["JobPosting"]] = relationship("JobPosting", back_populates="connector")


class SourceTarget(Base):
    __tablename__ = "source_targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    connector_id: Mapped[int] = mapped_column(Integer, ForeignKey("connectors.id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    company_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_tenant_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    connector: Mapped["Connector"] = relationship("Connector", back_populates="source_targets")
    fetch_run_targets: Mapped[list["FetchRunTarget"]] = relationship(
        "FetchRunTarget", back_populates="source_target"
    )
    job_postings: Mapped[list["JobPosting"]] = relationship("JobPosting", back_populates="source_target")


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="running", nullable=False)
    requested_connectors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    requested_target_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    total_jobs_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_jobs_normalized: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_jobs_matched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="fetch_runs")
    fetch_run_targets: Mapped[list["FetchRunTarget"]] = relationship(
        "FetchRunTarget", back_populates="fetch_run"
    )
    job_matches: Mapped[list["JobMatch"]] = relationship("JobMatch", back_populates="fetch_run")


class FetchRunTarget(Base):
    __tablename__ = "fetch_run_targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    fetch_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("fetch_runs.id"), nullable=False)
    source_target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_targets.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    jobs_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    fetch_run: Mapped["FetchRun"] = relationship("FetchRun", back_populates="fetch_run_targets")
    source_target: Mapped["SourceTarget"] = relationship(
        "SourceTarget", back_populates="fetch_run_targets"
    )


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("connector_id", "source_target_id", "external_id", name="uq_job_source"),
        Index("ix_job_postings_connector_id", "connector_id"),
        Index("ix_job_postings_source_target_id", "source_target_id"),
        Index("ix_job_postings_posted_at", "posted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    connector_id: Mapped[int] = mapped_column(Integer, ForeignKey("connectors.id"), nullable=False)
    source_target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_targets.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    connector: Mapped["Connector"] = relationship("Connector", back_populates="job_postings")
    source_target: Mapped["SourceTarget"] = relationship("SourceTarget", back_populates="job_postings")
    job_matches: Mapped[list["JobMatch"]] = relationship("JobMatch", back_populates="job")


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        Index("ix_job_matches_profile_score", "profile_id", "overall_score"),
        Index("ix_job_matches_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_postings.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=False)
    fetch_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("fetch_runs.id"), nullable=True
    )
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    title_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    skills_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    level_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    location_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    job: Mapped["JobPosting"] = relationship("JobPosting", back_populates="job_matches")
    profile: Mapped["Profile"] = relationship("Profile", back_populates="job_matches")
    fetch_run: Mapped["FetchRun"] = relationship("FetchRun", back_populates="job_matches")


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (
        UniqueConstraint("profile_id", "job_id", name="uq_saved_jobs_profile_job"),
        Index("ix_saved_jobs_profile_id", "profile_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="saved")
    saved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApplicationDraft(Base):
    __tablename__ = "application_drafts"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "saved_job_id", name="uq_application_drafts_profile_saved_job"
        ),
        Index("ix_application_drafts_profile_id", "profile_id"),
        Index("ix_application_drafts_saved_job_id", "saved_job_id"),
        Index("ix_application_drafts_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    saved_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="review_pending")
    fit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyword_gap_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tailored_resume_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tailored_resume_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    qa_answers_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    intent_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"
    __table_args__ = (
        Index("ix_tailored_resumes_profile_id", "profile_id"),
        Index("ix_tailored_resumes_saved_job_id", "saved_job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    saved_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False
    )
    latex_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_bytes: Mapped[bytes | None] = mapped_column(sa.LargeBinary, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ScheduledFetch(Base):
    __tablename__ = "scheduled_fetches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    connectors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
