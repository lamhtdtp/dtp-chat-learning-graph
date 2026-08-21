"""add study_sessions (thời lượng học — REQ §3.6/§7)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-19 11:00:00.000000

Không dựng lại được dữ liệu quá khứ: trước đây không có gì lưu thời gian học nên
bảng bắt đầu từ rỗng. Hồ sơ học tập sẽ nói rõ điều đó thay vì hiện 0 phút.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'study_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('mo_luc', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('dong_luc', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('so_giay', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('so_hoi', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['topic_id'], ['curriculum_topics.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_study_sessions_user_id'), 'study_sessions', ['user_id'])
    op.create_index(op.f('ix_study_sessions_topic_id'), 'study_sessions', ['topic_id'])
    op.create_index(op.f('ix_study_sessions_mo_luc'), 'study_sessions', ['mo_luc'])


def downgrade() -> None:
    for i in ('mo_luc', 'topic_id', 'user_id'):
        op.drop_index(op.f(f'ix_study_sessions_{i}'), table_name='study_sessions')
    op.drop_table('study_sessions')
