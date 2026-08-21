"""add curriculum_topics.tu_ma_tran (cảnh báo đơn vị do nạp ma trận tạo — §2.5)

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-08-20 11:00:00.000000

Giữ hành vi tự tạo đơn vị khi nạp .docx (quyết định (b)), nhưng ĐÁNH DẤU lại để
CMS cảnh báo được. Không đánh dấu thì chuyên gia không có cách nào biết danh mục
vừa phình thêm mấy đơn vị tên lấy thô từ Word.

Dòng cũ để false: không suy ngược được cái nào từng do ma trận tạo.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('curriculum_topics',
                  sa.Column('tu_ma_tran', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('curriculum_topics', 'tu_ma_tran')
