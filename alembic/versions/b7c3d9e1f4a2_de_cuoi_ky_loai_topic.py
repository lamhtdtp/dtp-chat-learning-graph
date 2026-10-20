"""de_cuoi_ky.loai + topic_id — dùng chung chỗ lưu đề đã rút cho "Luyện thêm" (US-25)

Revision ID: b7c3d9e1f4a2
Revises: a1d5e2f3b4c6
Create Date: 2026-10-20 10:00:00.000000

Lượt luyện thêm có cùng nhu cầu với đề cuối kỳ: lưu bản câu (kèm đáp án) phía máy
chủ lúc rút để lúc nộp chấm đúng bản học sinh đã thấy, nộp hai lần chỉ ghi một
lần. Dùng lại bảng thay vì dựng bảng thứ hai y hệt, nhưng phải phân loại — nếu
không, lịch sử / "xoá tất cả" của đề cuối kỳ sẽ liệt kê và xoá luôn lượt luyện thêm.

* `loai`: 'cuoi_ky' (mặc định, nên mọi dòng cũ vẫn đúng) | 'luyen_them'.
* `topic_id`: bài của lượt luyện thêm; NULL với đề cuối kỳ (phủ cả học kỳ).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c3d9e1f4a2'
down_revision: Union[str, Sequence[str], None] = 'a1d5e2f3b4c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('de_cuoi_ky', sa.Column('loai', sa.String(), server_default='cuoi_ky', nullable=False))
    op.add_column('de_cuoi_ky', sa.Column('topic_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_de_cuoi_ky_topic_id', 'de_cuoi_ky', 'curriculum_topics',
                          ['topic_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_de_cuoi_ky_loai'), 'de_cuoi_ky', ['loai'], unique=False)
    op.create_index(op.f('ix_de_cuoi_ky_topic_id'), 'de_cuoi_ky', ['topic_id'], unique=False)


def downgrade() -> None:
    # Bỏ cột `loai` mà giữ dòng luyện thêm thì chúng hoá thành "đề cuối kỳ" và hiện
    # trong lịch sử cuối kỳ của học sinh -> xoá chúng (lần nộp đã ghi ở
    # quiz_attempts với nguon='luyen_them' vẫn còn, không mất kết quả).
    op.execute("DELETE FROM de_cuoi_ky WHERE loai = 'luyen_them'")
    op.drop_index(op.f('ix_de_cuoi_ky_topic_id'), table_name='de_cuoi_ky')
    op.drop_index(op.f('ix_de_cuoi_ky_loai'), table_name='de_cuoi_ky')
    op.drop_constraint('fk_de_cuoi_ky_topic_id', 'de_cuoi_ky', type_='foreignkey')
    op.drop_column('de_cuoi_ky', 'topic_id')
    op.drop_column('de_cuoi_ky', 'loai')
