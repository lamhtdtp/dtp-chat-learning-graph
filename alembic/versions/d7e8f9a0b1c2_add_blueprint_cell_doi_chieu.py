"""add blueprint_cells.ten_nguon/mach_nguon/diem_khop (đối chiếu ma trận §2.5)

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-08-20 09:00:00.000000

Bảng đối chiếu cần biết tên NGUYÊN VĂN trong .docx và điểm khớp lúc gán. Sau khi
nạp, tên gốc không còn ở đâu -> không tính lại được (so tên đã gán với chính nó
luôn ra 100%, bảng thành vô nghĩa).

Dòng nạp TRƯỚC thay đổi này để NULL: UI hiện "chưa có dữ liệu đối chiếu" thay vì
bịa ra một con số.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('blueprint_cells', sa.Column('ten_nguon', sa.String(), nullable=True))
    op.add_column('blueprint_cells', sa.Column('mach_nguon', sa.String(), nullable=True))
    op.add_column('blueprint_cells', sa.Column('diem_khop', sa.Float(), nullable=True))


def downgrade() -> None:
    for c in ('diem_khop', 'mach_nguon', 'ten_nguon'):
        op.drop_column('blueprint_cells', c)
