"""add structured resume parsing + embedding columns for agentic matching

Revision ID: 008
Revises: 007
Create Date: 2026-08-07
"""
import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("parsed_experience", sa.JSON, nullable=True))
    op.add_column("profiles", sa.Column("embedding", sa.JSON, nullable=True))
    op.add_column("job_postings", sa.Column("embedding", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("job_postings", "embedding")
    op.drop_column("profiles", "embedding")
    op.drop_column("profiles", "parsed_experience")
