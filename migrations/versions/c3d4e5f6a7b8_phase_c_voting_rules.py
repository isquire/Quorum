"""Phase C: per-motion voting rules, custom stage sequence, notification, acting chair

Adds:
- motions.deacons_only (Boolean) — Constitution Art VIII §6
- meetings.acting_chair_id (FK to users) — Bylaws Art I §2
- meeting_attendances.notified_at (DateTime) — Bylaws Art I §§2-3

The MeetingStage, MotionType enums are extended in the model code but
since we use native_enum=False (VARCHAR-backed), no DDL change is needed
for those; the new string values are simply stored as-is.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    # --- motions.deacons_only ---
    with op.batch_alter_table("motions") as batch_op:
        batch_op.add_column(
            sa.Column("deacons_only", sa.Boolean(), nullable=False, server_default="0")
        )

    # --- meetings.acting_chair_id ---
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.add_column(
            sa.Column("acting_chair_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_meeting_acting_chair",
            "users",
            ["acting_chair_id"],
            ["id"],
        )

    # --- meeting_attendances.notified_at ---
    with op.batch_alter_table("meeting_attendances") as batch_op:
        batch_op.add_column(
            sa.Column("notified_at", sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("meeting_attendances") as batch_op:
        batch_op.drop_column("notified_at")

    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_constraint("fk_meeting_acting_chair", type_="foreignkey")
        batch_op.drop_column("acting_chair_id")

    with op.batch_alter_table("motions") as batch_op:
        batch_op.drop_column("deacons_only")
