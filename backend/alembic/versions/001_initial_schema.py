"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "connectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("auth_mode", sa.String(50), server_default="public", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("raw_resume_path", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("preferred_titles", sa.JSON(), nullable=True),
        sa.Column("preferred_level", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "source_targets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("connector_id", sa.Integer(), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("company_name", sa.String(300), nullable=False),
        sa.Column("company_key", sa.String(200), nullable=True),
        sa.Column("target_slug", sa.String(200), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("external_tenant_id", sa.String(200), nullable=True),
        sa.Column("region_hint", sa.String(100), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(50), server_default="running", nullable=False),
        sa.Column("requested_connectors", sa.JSON(), nullable=True),
        sa.Column("requested_target_ids", sa.JSON(), nullable=True),
        sa.Column("total_jobs_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_jobs_normalized", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_jobs_matched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "fetch_run_targets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("fetch_run_id", sa.String(36), sa.ForeignKey("fetch_runs.id"), nullable=False),
        sa.Column(
            "source_target_id", sa.String(36), sa.ForeignKey("source_targets.id"), nullable=False
        ),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("jobs_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_postings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("connector_id", sa.Integer(), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column(
            "source_target_id", sa.String(36), sa.ForeignKey("source_targets.id"), nullable=False
        ),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("canonical_key", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(300), nullable=False),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("raw_description", sa.Text(), nullable=True),
        sa.Column("normalized_level", sa.String(50), nullable=True),
        sa.Column("employment_type", sa.String(100), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "source_target_id", "external_id", name="uq_job_source"),
    )
    op.create_index("ix_job_postings_connector_id", "job_postings", ["connector_id"])
    op.create_index("ix_job_postings_source_target_id", "job_postings", ["source_target_id"])
    op.create_index("ix_job_postings_posted_at", "job_postings", ["posted_at"])

    op.create_table(
        "job_matches",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id"), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("fetch_run_id", sa.String(36), sa.ForeignKey("fetch_runs.id"), nullable=True),
        sa.Column("overall_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("title_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("skills_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("level_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("location_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_matches_profile_score", "job_matches", ["profile_id", "overall_score"])
    op.create_index("ix_job_matches_job_id", "job_matches", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_matches")
    op.drop_table("job_postings")
    op.drop_table("fetch_run_targets")
    op.drop_table("fetch_runs")
    op.drop_table("source_targets")
    op.drop_table("profiles")
    op.drop_table("connectors")
    op.drop_table("users")
