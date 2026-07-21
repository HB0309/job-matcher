"""add saved_jobs table

Revision ID: 003
Revises: 002
Create Date: 2026-05-04
"""
import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="saved"),
        sa.Column("saved_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("profile_id", "job_id", name="uq_saved_jobs_profile_job"),
    )
    op.create_index("ix_saved_jobs_profile_id", "saved_jobs", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_jobs_profile_id", table_name="saved_jobs")
    op.drop_table("saved_jobs")
