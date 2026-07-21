"""add scheduled_fetches table

Revision ID: 004
Revises: 003
Create Date: 2026-05-07
"""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_fetches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connectors", sa.JSON(), nullable=True),
        sa.Column("interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scheduled_fetches_profile_id", "scheduled_fetches", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_fetches_profile_id", table_name="scheduled_fetches")
    op.drop_table("scheduled_fetches")
