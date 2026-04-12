"""Add meeting templates and document repository tables

Meeting templates allow admins to save reusable agenda item sets.
The document repository stores governance documents with version history.

Revision ID: g7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-12 23:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "g7a8b9c0d1e2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    # Meeting templates
    op.create_table(
        "meeting_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("meeting_type", sa.String(50), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"],
            name="fk_meeting_template_created_by",
        ),
    )

    op.create_table(
        "meeting_template_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_confidential", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["meeting_templates.id"],
            name="fk_template_item_template",
        ),
    )

    # Document repository
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"],
            name="fk_document_updated_by",
        ),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("change_summary", sa.String(500), nullable=False, server_default=""),
        sa.Column("edited_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_doc_version_document",
        ),
        sa.ForeignKeyConstraint(
            ["edited_by_id"], ["users.id"],
            name="fk_doc_version_edited_by",
        ),
    )


def downgrade():
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("meeting_template_items")
    op.drop_table("meeting_templates")
