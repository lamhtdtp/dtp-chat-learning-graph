"""add topic_content.nhac_json (lời nhắc chủ động của trợ lý)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-11 10:00:00.000000

Trợ lý chủ động (lát 4): đọc xong phần khái niệm thì hỏi lại một câu kiểm tra
hiểu. Nội dung sinh MỘT LẦN lúc biên soạn rồi cache tại cột này — y hệt
quiz_json — để lúc học sinh đọc bài không phải gọi LLM và không trừ hạn mức
lượt hỏi trong ngày.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'topic_content',
        sa.Column('nhac_json', sa.Text(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('topic_content', 'nhac_json')
