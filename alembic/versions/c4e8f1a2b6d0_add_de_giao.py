"""de_giao + de_cuoi_ky.de_giao_id — giáo viên giao đề cuối kỳ bằng mã (US-26)

Revision ID: c4e8f1a2b6d0
Revises: b7c3d9e1f4a2
Create Date: 2026-10-20 15:00:00.000000

* `de_giao`: đề giáo viên rút một lần, kèm mã 6 ký tự (NULL khi còn nháp, unique).
* `de_cuoi_ky.de_giao_id`: bài theo mã của học sinh (loai='de_giao'), unique cùng
  `user_id` — một em một bài cho mỗi mã, kể cả khi nộp từ hai thiết bị cùng lúc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8f1a2b6d0'
down_revision: Union[str, Sequence[str], None] = 'b7c3d9e1f4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'de_giao',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ma', sa.String(), nullable=True),
        sa.Column('nguoi_tao_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('exam', sa.String(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('so_cau', sa.Integer(), nullable=False),
        sa.Column('tham_so_json', sa.Text(), nullable=False),
        sa.Column('thong_bao', sa.Text(), nullable=False, server_default=''),
        sa.Column('cau_json', sa.Text(), nullable=False),
        sa.Column('trang_thai', sa.String(), nullable=False, server_default='nhap'),
        sa.Column('dong_luc', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('clock_timestamp()')),
        sa.UniqueConstraint('ma', name='uq_de_giao_ma'),
    )
    op.create_index(op.f('ix_de_giao_nguoi_tao_id'), 'de_giao', ['nguoi_tao_id'], unique=False)

    op.add_column('de_cuoi_ky', sa.Column('de_giao_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_de_cuoi_ky_de_giao_id', 'de_cuoi_ky', 'de_giao', ['de_giao_id'], ['id'])
    op.create_index(op.f('ix_de_cuoi_ky_de_giao_id'), 'de_cuoi_ky', ['de_giao_id'], unique=False)
    op.create_unique_constraint('uq_de_cuoi_ky_de_giao_user', 'de_cuoi_ky', ['de_giao_id', 'user_id'])


def downgrade() -> None:
    # Bài theo mã không còn chỗ gắn vào đề giao -> xoá (nếu giữ, chúng hoá thành
    # "đề cuối kỳ" hiện trong lịch sử với loai lạ). Lần nộp ở quiz_attempts
    # (nguon='de_giao') vẫn còn nên không mất thống kê YCCĐ.
    op.execute("DELETE FROM de_cuoi_ky WHERE loai = 'de_giao'")
    op.drop_constraint('uq_de_cuoi_ky_de_giao_user', 'de_cuoi_ky', type_='unique')
    op.drop_index(op.f('ix_de_cuoi_ky_de_giao_id'), table_name='de_cuoi_ky')
    op.drop_constraint('fk_de_cuoi_ky_de_giao_id', 'de_cuoi_ky', type_='foreignkey')
    op.drop_column('de_cuoi_ky', 'de_giao_id')
    op.drop_index(op.f('ix_de_giao_nguoi_tao_id'), table_name='de_giao')
    op.drop_table('de_giao')
