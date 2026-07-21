"""add tailored_resumes table

Revision ID: 007
Revises: 006
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tailored_resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("saved_job_id", sa.String(36), sa.ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latex_source", sa.Text, nullable=True),
        sa.Column("pdf_bytes", sa.LargeBinary, nullable=True),
        sa.Column("user_notes", sa.Text, nullable=True),
        sa.Column("gemini_analysis", sa.JSON, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tailored_resumes_profile_id", "tailored_resumes", ["profile_id"])
    op.create_index("ix_tailored_resumes_saved_job_id", "tailored_resumes", ["saved_job_id"])


def downgrade() -> None:
    op.drop_index("ix_tailored_resumes_saved_job_id", table_name="tailored_resumes")
    op.drop_index("ix_tailored_resumes_profile_id", table_name="tailored_resumes")
    op.drop_table("tailored_resumes")
