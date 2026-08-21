"""add 4 phần nội dung mới + bo_cuc_json (REQ-demo-v2 §1.2)

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-19 09:00:00.000000

Mô hình 7 phần. Ba cột cũ giữ nguyên tên: khai_niem = phần ③ Kiến thức trọng tâm,
minh_hoa_json = ④, vi_du_json = ⑤. Thêm 4 phần còn lại + bố cục.

KHÔNG backfill bo_cuc_json: rỗng nghĩa là "thứ tự chuẩn, không ẩn gì" nên mọi bản
ghi cũ mở bình thường. Nhồi mảng 7 phần vào từng dòng chỉ tạo dữ liệu chết.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PHAN = ('khoi_dong', 'hoat_dong', 'luyen_tap', 'bai_tap')


def upgrade() -> None:
    for c in _PHAN:
        op.add_column('topic_content',
                      sa.Column(c, sa.Text(), nullable=False, server_default=''))
    op.add_column('topic_content',
                  sa.Column('bo_cuc_json', sa.Text(), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('topic_content', 'bo_cuc_json')
    for c in reversed(_PHAN):
        op.drop_column('topic_content', c)
