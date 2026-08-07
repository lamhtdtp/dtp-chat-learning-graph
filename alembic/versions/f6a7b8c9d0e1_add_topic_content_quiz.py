"""add topic_content.quiz_json (Kiểm tra nhanh sinh theo ma trận)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-06 10:00:00.000000

Phần ④ "Kiểm tra nhanh" của bài học: trắc nghiệm sinh tự động theo ma trận đặc
tả rồi cache vào cột này (P3). Không nhập tay.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'topic_content',
        sa.Column('quiz_json', sa.Text(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('topic_content', 'quiz_json')
