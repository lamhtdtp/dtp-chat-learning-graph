"""add topic_content + student_progress (giáo trình có cấu trúc)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-06 09:00:00.000000

Mô hình giáo trình số (theo mockup): nội dung bài học 4 phần cho từng đơn vị
kiến thức + tiến độ học sinh theo đơn vị.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'topic_content',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('curriculum_topics.id'), nullable=False),
        sa.Column('khai_niem', sa.Text(), nullable=False, server_default=''),
        sa.Column('minh_hoa_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('vi_du_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('day_json', sa.Text(), nullable=True),
        sa.Column('nguon', sa.String(), nullable=True),
        sa.Column('trang_thai', sa.String(), nullable=False, server_default='draft'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_topic_content_topic_id', 'topic_content', ['topic_id'], unique=True)

    op.create_table(
        'student_progress',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('curriculum_topics.id'), nullable=False),
        sa.Column('trang_thai', sa.String(), nullable=False, server_default='dang'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'topic_id', name='uq_student_progress_user_topic'),
    )
    op.create_index('ix_student_progress_user_id', 'student_progress', ['user_id'])
    op.create_index('ix_student_progress_topic_id', 'student_progress', ['topic_id'])


def downgrade() -> None:
    op.drop_table('student_progress')
    op.drop_table('topic_content')
