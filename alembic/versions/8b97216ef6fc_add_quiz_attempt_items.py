"""add quiz_attempt_items (chi tiết từng câu, khoá bền theo yêu cầu cần đạt)

Revision ID: 8b97216ef6fc
Revises: c8d9e0f1a2b3
Create Date: 2026-10-17 11:15:09.901371

Nền cho "từ kết quả, gợi ý tài liệu bổ sung + bài làm mới chọn theo YCCĐ".

`quiz_attempts` trước giờ chỉ có điểm tổng, CỐ Ý không lưu học sinh chọn gì vì
chỉ số câu sẽ trỏ sai đề sau khi quiz được sinh lại. Bảng này lưu được nhờ khoá
bền thay thế: `ycd_key` (nguyên văn yêu cầu cần đạt đã chuẩn hoá) và `ar_id`
(mã YCCĐ bên DTP Testbank).

KHÔNG đặt khoá ngoại tới `blueprint_cells.id`: nạp lại ma trận là xoá sạch cell
cũ (app/seed_matrix.py, app/seed_curriculum.py), khoá ngoại sẽ chết đúng kiểu mà
bảng này sinh ra để tránh.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b97216ef6fc'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quiz_attempt_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('attempt_id', sa.Integer(), nullable=False),
        sa.Column('ycd_key', sa.Text(), nullable=False, server_default=''),
        sa.Column('ycd_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('ar_id', sa.String(), nullable=True),
        sa.Column('qid', sa.String(), nullable=True),
        sa.Column('phan', sa.String(), nullable=False, server_default=''),
        sa.Column('muc_do', sa.String(), nullable=False, server_default=''),
        sa.Column('chon', sa.String(), nullable=False, server_default=''),
        sa.Column('dap_an', sa.String(), nullable=False, server_default=''),
        sa.Column('dung', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        # Xoá một lần nộp thì chi tiết đi theo: chi tiết không có nghĩa khi đứng rời.
        sa.ForeignKeyConstraint(['attempt_id'], ['quiz_attempts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_quiz_attempt_items_attempt_id'), 'quiz_attempt_items', ['attempt_id'], unique=False
    )
    op.create_index(
        op.f('ix_quiz_attempt_items_ar_id'), 'quiz_attempt_items', ['ar_id'], unique=False
    )
    # Truy vấn chính của tính năng: "yêu cầu cần đạt nào em còn yếu" — gom theo
    # ycd_key sau khi đã lọc theo học sinh. Vế lọc học sinh nằm ở bảng cha và đã
    # có ix_quiz_attempts_user_id lo; index này lo phần gom.
    op.create_index(
        op.f('ix_quiz_attempt_items_ycd_key'), 'quiz_attempt_items', ['ycd_key'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_quiz_attempt_items_ycd_key'), table_name='quiz_attempt_items')
    op.drop_index(op.f('ix_quiz_attempt_items_ar_id'), table_name='quiz_attempt_items')
    op.drop_index(op.f('ix_quiz_attempt_items_attempt_id'), table_name='quiz_attempt_items')
    op.drop_table('quiz_attempt_items')
