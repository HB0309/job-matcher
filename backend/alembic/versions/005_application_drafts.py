"""add application_drafts table

Revision ID: 005
Revises: 004
Create Date: 2026-05-07
"""
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_job_id",
            sa.String(36),
            sa.ForeignKey("saved_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("job_postings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="review_pending"),
        sa.Column("fit_summary", sa.Text(), nullable=True),
        sa.Column("keyword_gap_summary", sa.JSON(), nullable=True),
        sa.Column("tailored_resume_json", sa.JSON(), nullable=True),
        sa.Column("tailored_resume_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("qa_answers_json", sa.JSON(), nullable=True),
        sa.Column("intent_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("profile_id", "saved_job_id", name="uq_application_drafts_profile_saved_job"),
    )
    op.create_index("ix_application_drafts_profile_id", "application_drafts", ["profile_id"])
    op.create_index("ix_application_drafts_saved_job_id", "application_drafts", ["saved_job_id"])
    op.create_index("ix_application_drafts_status", "application_drafts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_application_drafts_status", table_name="application_drafts")
    op.drop_index("ix_application_drafts_saved_job_id", table_name="application_drafts")
    op.drop_index("ix_application_drafts_profile_id", table_name="application_drafts")
    op.drop_table("application_drafts")
