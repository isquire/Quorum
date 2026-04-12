"""Phase B: boards, board memberships, role expansion, family_group

Adds the Board and BoardMembership tables for the two-board governance
model (Board of Deacons, Board of Administration) plus the Assembly.
Extends the Role enum with pastor, deacon, trustee, assistant_treasurer.
Adds Meeting.board_id FK and User.family_group.

Seeds the three canonical boards.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-12 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create boards table.
    op.create_table(
        'boards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )

    # 2. Create board_memberships table.
    op.create_table(
        'board_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('board_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_on_board', sa.String(length=50), nullable=False,
                  server_default='member'),
        sa.Column('is_voting', sa.Boolean(), nullable=False,
                  server_default=sa.text('1')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.ForeignKeyConstraint(['board_id'], ['boards.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('board_id', 'user_id', name='uq_board_membership'),
    )

    # 3. Add columns to users table.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('family_group', sa.String(length=100), nullable=True)
        )

    # 4. Add board_id to meetings table.
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('board_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_meeting_board', 'boards', ['board_id'], ['id']
        )

    # 5. Seed the three canonical boards.
    boards_table = sa.table(
        'boards',
        sa.column('id', sa.Integer),
        sa.column('slug', sa.String),
        sa.column('display_name', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    now = datetime.utcnow()
    op.bulk_insert(boards_table, [
        {'slug': 'assembly', 'display_name': 'Assembly',
         'created_at': now, 'updated_at': now},
        {'slug': 'board_of_deacons', 'display_name': 'Board of Deacons',
         'created_at': now, 'updated_at': now},
        {'slug': 'board_of_administration',
         'display_name': 'Board of Administration',
         'created_at': now, 'updated_at': now},
    ])

    # 6. Backfill existing meetings to Board of Administration.
    #    Use raw SQL since we just seeded the boards.
    op.execute(
        "UPDATE meetings SET board_id = "
        "(SELECT id FROM boards WHERE slug = 'board_of_administration') "
        "WHERE board_id IS NULL"
    )


def downgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_meeting_board', type_='foreignkey')
        batch_op.drop_column('board_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('family_group')

    op.drop_table('board_memberships')
    op.drop_table('boards')
