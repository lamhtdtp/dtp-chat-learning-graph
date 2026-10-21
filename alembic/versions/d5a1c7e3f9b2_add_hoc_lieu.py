"""hoc_lieu — kho học liệu có mã gắn theo YCCĐ / câu / phương án (US-27)

Revision ID: d5a1c7e3f9b2
Revises: c4e8f1a2b6d0
Create Date: 2026-10-21 10:00:00.000000

Dữ liệu cấu trúc do người biên soạn nhập (không embed, không vector DB). `ma` lưu CHỮ
HOA và unique: hai quản trị viên thêm cùng một mã cùng lúc thì UNIQUE ở đây là chốt
cuối (kiểm-rồi-chèn ở tầng ứng dụng thua cuộc đua). Xoá MỀM (`xoa_luc`) nên dòng còn
đó và mã không bao giờ dùng lại — bài cũ của học sinh khỏi trỏ nhầm sang học liệu khác.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5a1c7e3f9b2'
down_revision: Union[str, Sequence[str], None] = 'c4e8f1a2b6d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hoc_lieu',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ma', sa.String(length=64), nullable=False),
        sa.Column('loai', sa.String(length=8), nullable=False),
        sa.Column('nhan', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=1024), nullable=False),
        sa.Column('muc_dich', sa.String(length=8), nullable=False),
        sa.Column('ycd_key', sa.Text(), nullable=False),
        sa.Column('ycd_text', sa.Text(), nullable=False),
        sa.Column('qid', sa.String(), nullable=True),
        sa.Column('option_key', sa.String(length=8), nullable=True),
        sa.Column('nguoi_tao_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('tao_luc', sa.DateTime(), nullable=False, server_default=sa.text('clock_timestamp()')),
        sa.Column('nguoi_sua_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('sua_luc', sa.DateTime(), nullable=True),
        sa.Column('xoa_luc', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('ma', name='uq_hoc_lieu_ma'),
    )
    op.create_index(op.f('ix_hoc_lieu_ycd_key'), 'hoc_lieu', ['ycd_key'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hoc_lieu_ycd_key'), table_name='hoc_lieu')
    op.drop_table('hoc_lieu')
