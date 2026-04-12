"""Add archive fields to meetings/reports and admin_actions table

Admins can archive meetings and reports to hide them from normal views.
The admin_actions table records an audit log of every admin action.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-12 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    # --- Archive fields on meetings ---
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.add_column(
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column("archived_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("archived_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
        )

    # --- Archive fields on reports ---
    with op.batch_alter_table("reports") as batch_op:
        batch_op.add_column(
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column("archived_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("archived_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
        )

    # --- Admin actions audit log ---
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )


def downgrade():
    op.drop_table("admin_actions")

    with op.batch_alter_table("reports") as batch_op:
        batch_op.drop_column("archived_by_id")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("is_archived")

    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_column("archived_by_id")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("is_archived")
