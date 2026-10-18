"""đề cuối kỳ từ DTP Testbank: de_cuoi_ky, ly_do_phuong_an, quiz_attempts.topic_id nullable

Revision ID: 9c4e1a7b2d30
Revises: 8b97216ef6fc
Create Date: 2026-10-18 09:00:00.000000

- `de_cuoi_ky`: đề đã rút cho một học sinh, kèm đáp án (chỉ đọc ở máy chủ) để
  chấm đúng bản nội dung học sinh đã thấy.
- `ly_do_phuong_an`: vì sao từng phương án đúng/sai, theo (qid, version,
  option_key, nguon). Tạm sinh bằng AI; testbank có `rationale` thì thêm nguồn.
- `quiz_attempts.topic_id` NULL được: một lần nộp đề cuối kỳ phủ cả học kỳ, không
  thuộc bài nào (nguon = "cuoi_ky"). Chi tiết theo YCCĐ nằm ở quiz_attempt_items.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c4e1a7b2d30'
down_revision: Union[str, Sequence[str], None] = '8b97216ef6fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'de_cuoi_ky',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tham_so_json', sa.Text(), nullable=False),
        sa.Column('thong_bao', sa.Text(), nullable=False, server_default=''),
        sa.Column('cau_json', sa.Text(), nullable=False),
        sa.Column('ket_qua_json', sa.Text(), nullable=True),
        sa.Column('nop_luc', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_de_cuoi_ky_user_id'), 'de_cuoi_ky', ['user_id'], unique=False)

    op.create_table(
        'ly_do_phuong_an',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('qid', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('option_key', sa.String(), nullable=False),
        sa.Column('noi_dung', sa.Text(), nullable=False),
        sa.Column('nguon', sa.String(), nullable=False, server_default='ai'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('qid', 'version', 'option_key', 'nguon'),
    )
    op.create_index(op.f('ix_ly_do_phuong_an_qid'), 'ly_do_phuong_an', ['qid'], unique=False)

    op.alter_column('quiz_attempts', 'topic_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Xoá lần nộp đề cuối kỳ trước khi ép NOT NULL lại (chi tiết đi theo CASCADE).
    op.execute("DELETE FROM quiz_attempts WHERE topic_id IS NULL")
    op.alter_column('quiz_attempts', 'topic_id', existing_type=sa.Integer(), nullable=False)
    op.drop_index(op.f('ix_ly_do_phuong_an_qid'), table_name='ly_do_phuong_an')
    op.drop_table('ly_do_phuong_an')
    op.drop_index(op.f('ix_de_cuoi_ky_user_id'), table_name='de_cuoi_ky')
    op.drop_table('de_cuoi_ky')
