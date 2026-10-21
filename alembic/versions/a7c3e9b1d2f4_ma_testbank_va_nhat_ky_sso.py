"""bài theo mã Testbank (US-29) + nhật ký cấp phiếu SSO sang Testbank (US-28)

Revision ID: a7c3e9b1d2f4
Revises: d5a1c7e3f9b2
Create Date: 2026-10-21 15:00:00.000000

`de_cuoi_ky` thêm 4 cột cho bài theo mã Testbank (loai="testbank"): mã, khoá bài làm (bí
mật, chỉ ở máy chủ), tiêu đề lượt phát, bản chép câu trả lời. Unique (user_id, ma_testbank):
Testbank mức 0 mỗi lần vào thi là một bài mới nên "mỗi em một bài cho mỗi mã" phải do
learning chốt. Postgres coi các NULL là khác nhau nên đề tự rút / đề giao cũ không vướng.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c3e9b1d2f4'
down_revision: Union[str, Sequence[str], None] = 'd5a1c7e3f9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('de_cuoi_ky', sa.Column('ma_testbank', sa.String(length=8), nullable=True))
    op.add_column('de_cuoi_ky', sa.Column('khoa_bai_lam', sa.Text(), nullable=True))
    op.add_column('de_cuoi_ky', sa.Column('tieu_de', sa.Text(), nullable=True))
    op.add_column('de_cuoi_ky', sa.Column('tra_loi_json', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_de_cuoi_ky_testbank_user', 'de_cuoi_ky', ['user_id', 'ma_testbank'])

    op.create_table(
        'nhat_ky_sso_testbank',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('vai', sa.String(length=20), nullable=False),
        sa.Column('jti', sa.String(length=36), nullable=True),
        sa.Column('ket_qua', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('clock_timestamp()')),
    )
    op.create_index(op.f('ix_nhat_ky_sso_testbank_user_id'), 'nhat_ky_sso_testbank', ['user_id'])
    op.create_index(op.f('ix_nhat_ky_sso_testbank_email'), 'nhat_ky_sso_testbank', ['email'])


def downgrade() -> None:
    op.drop_index(op.f('ix_nhat_ky_sso_testbank_email'), table_name='nhat_ky_sso_testbank')
    op.drop_index(op.f('ix_nhat_ky_sso_testbank_user_id'), table_name='nhat_ky_sso_testbank')
    op.drop_table('nhat_ky_sso_testbank')
    op.drop_constraint('uq_de_cuoi_ky_testbank_user', 'de_cuoi_ky', type_='unique')
    op.drop_column('de_cuoi_ky', 'tra_loi_json')
    op.drop_column('de_cuoi_ky', 'tieu_de')
    op.drop_column('de_cuoi_ky', 'khoa_bai_lam')
    op.drop_column('de_cuoi_ky', 'ma_testbank')
