"""Phase A: add users.is_active_member column

Bylaws Art III §5 — tracks active membership for quorum denominator.
Constitution Art VIII §4 uses 'active members' as the quorum base for
assembly (congregational) meetings.

Revision ID: a1b2c3d4e5f6
Revises: 6778c73c56c7
Create Date: 2026-04-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '6778c73c56c7'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_active_member column with server default so existing rows
    # are backfilled as True (active).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_active_member',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('1'),
            )
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_active_member')
