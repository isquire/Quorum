"""Add document_id column to attachments table

Allow files to be attached to documents in the document repository.
Updates the single-parent check constraint to include document_id.

Revision ID: h8b9c0d1e2f3
Revises: g7a8b9c0d1e2
Create Date: 2026-04-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "h8b9c0d1e2f3"
down_revision = "g7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("attachments") as batch_op:
        batch_op.add_column(
            sa.Column("document_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_attachment_document",
            "documents",
            ["document_id"],
            ["id"],
        )
        batch_op.drop_constraint("ck_attachment_single_parent")
        batch_op.create_check_constraint(
            "ck_attachment_single_parent",
            "(CASE WHEN meeting_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN agenda_item_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN report_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN document_id IS NULL THEN 0 ELSE 1 END) = 1",
        )


def downgrade():
    with op.batch_alter_table("attachments") as batch_op:
        batch_op.drop_constraint("ck_attachment_single_parent")
        batch_op.drop_constraint("fk_attachment_document")
        batch_op.drop_column("document_id")
        batch_op.create_check_constraint(
            "ck_attachment_single_parent",
            "(CASE WHEN meeting_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN agenda_item_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN report_id IS NULL THEN 0 ELSE 1 END) = 1",
        )
