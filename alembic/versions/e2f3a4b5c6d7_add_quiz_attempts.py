"""add quiz_attempts (lưu từng lần học sinh nộp Kiểm tra nhanh)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-08 14:00:00.000000

Trước đây chấm xong là vứt: chỉ còn cờ dat|dang trong student_progress. Giáo viên
không xem lại được học sinh làm mấy lần, điểm bao nhiêu, đơn vị nào cả lớp đuối.

Không backfill được — dữ liệu cũ đã mất, bảng bắt đầu từ rỗng.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quiz_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('diem', sa.Integer(), nullable=False),
        sa.Column('tong', sa.Integer(), nullable=False),
        sa.Column('dat', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['topic_id'], ['curriculum_topics.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quiz_attempts_user_id'), 'quiz_attempts', ['user_id'])
    op.create_index(op.f('ix_quiz_attempts_topic_id'), 'quiz_attempts', ['topic_id'])
    op.create_index(op.f('ix_quiz_attempts_created_at'), 'quiz_attempts', ['created_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_quiz_attempts_created_at'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_topic_id'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_user_id'), table_name='quiz_attempts')
    op.drop_table('quiz_attempts')
