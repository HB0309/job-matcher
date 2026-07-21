"""convert preferred_level to JSON list

Revision ID: 002
Revises: 001
Create Date: 2026-04-21
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Read existing values before schema change
    rows = conn.execute(sa.text("SELECT id, preferred_level FROM profiles")).fetchall()

    # Add a temporary column to hold the JSON list
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("preferred_level_new", sa.JSON(), nullable=True))

    # Migrate: wrap existing string value into a single-element list
    for row_id, level in rows:
        if level:
            # If already JSON-looking (starts with '['), keep as-is
            try:
                parsed = json.loads(level)
                new_val = json.dumps(parsed if isinstance(parsed, list) else [parsed])
            except (json.JSONDecodeError, TypeError):
                new_val = json.dumps([level])
        else:
            new_val = json.dumps([])
        conn.execute(
            sa.text("UPDATE profiles SET preferred_level_new = :v WHERE id = :id"),
            {"v": new_val, "id": row_id},
        )

    # Drop old column, rename new one
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.drop_column("preferred_level")
        batch_op.alter_column("preferred_level_new", new_column_name="preferred_level")


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, preferred_level FROM profiles")).fetchall()

    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("preferred_level_old", sa.String(50), nullable=True))

    for row_id, levels_json in rows:
        try:
            levels = json.loads(levels_json) if levels_json else []
            val = levels[0] if levels else None
        except (json.JSONDecodeError, TypeError):
            val = None
        conn.execute(
            sa.text("UPDATE profiles SET preferred_level_old = :v WHERE id = :id"),
            {"v": val, "id": row_id},
        )

    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.drop_column("preferred_level")
        batch_op.alter_column("preferred_level_old", new_column_name="preferred_level")
