"""Add is_confidential to agenda_items and minutes_entries

Supports confidential minutes: agenda items flagged confidential cause
all related minutes entries to be auto-flagged.  Non-officer users see
redacted placeholders when viewing or exporting minutes.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-12 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("agenda_items") as batch_op:
        batch_op.add_column(
            sa.Column("is_confidential", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )

    with op.batch_alter_table("minutes_entries") as batch_op:
        batch_op.add_column(
            sa.Column("is_confidential", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade():
    with op.batch_alter_table("minutes_entries") as batch_op:
        batch_op.drop_column("is_confidential")

    with op.batch_alter_table("agenda_items") as batch_op:
        batch_op.drop_column("is_confidential")
