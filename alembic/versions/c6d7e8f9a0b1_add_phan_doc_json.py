"""add study_sessions.phan_doc_json (nhãn "Đọc x/y phần" — REQ §3.6 khối 3)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-19 14:00:00.000000

Lưu ID các phần đã đọc, không lưu số lượng: đọc lại phần cũ không được cộng thêm,
và đổi bố cục thì mẫu số vẫn tính lại đúng theo số phần đang hiện.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('study_sessions',
                  sa.Column('phan_doc_json', sa.Text(), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('study_sessions', 'phan_doc_json')
