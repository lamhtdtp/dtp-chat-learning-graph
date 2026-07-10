"""add itest mirror (itest_questions, itest_topic_map)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-10 12:00:00.000000

EPIC-10 — mirror ngân hàng Itest (read-only sync) + ánh xạ taxonomy.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'itest_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('itest_id', sa.String(), nullable=False),
        sa.Column('tag_goc', sa.String(), nullable=False),
        sa.Column('question_type', sa.String(), nullable=False),
        sa.Column('noi_dung', sa.Text(), nullable=False),
        sa.Column('options_json', sa.Text(), nullable=True),
        sa.Column('dap_an', sa.Text(), nullable=True),
        sa.Column('loi_giai', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('itest_id'),
    )
    op.create_index(op.f('ix_itest_questions_itest_id'), 'itest_questions', ['itest_id'], unique=True)
    op.create_index(op.f('ix_itest_questions_tag_goc'), 'itest_questions', ['tag_goc'], unique=False)
    op.create_index(op.f('ix_itest_questions_content_hash'), 'itest_questions', ['content_hash'], unique=False)

    op.create_table(
        'itest_topic_map',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('itest_tag', sa.String(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=True),
        sa.Column('muc_do', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['topic_id'], ['curriculum_topics.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('itest_tag'),
    )
    op.create_index(op.f('ix_itest_topic_map_itest_tag'), 'itest_topic_map', ['itest_tag'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_itest_topic_map_itest_tag'), table_name='itest_topic_map')
    op.drop_table('itest_topic_map')
    op.drop_index(op.f('ix_itest_questions_content_hash'), table_name='itest_questions')
    op.drop_index(op.f('ix_itest_questions_tag_goc'), table_name='itest_questions')
    op.drop_index(op.f('ix_itest_questions_itest_id'), table_name='itest_questions')
    op.drop_table('itest_questions')
