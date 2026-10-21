"""bài theo mã mức 1 + chi tiết sau nộp + lý do theo tờ đề (US-30)

Revision ID: b3f7a1c9d2e5
Revises: a7c3e9b1d2f4
Create Date: 2026-10-21 18:00:00.000000

`de_cuoi_ky` thêm: `muc` (0 đường học sinh, 1 đường đối tác — cố định lúc tạo), `bai_lam_tb_id`
(mã bài làm Testbank của mức 1, bí mật), `chi_tiet_json` (bản chép chi tiết sau nộp), `dap_an_mo`
(đã chép bản có đáp án), `het_han_dap_an` (Testbank trả 410 trước khi chép được), `kiem_luc` (lần hỏi
Testbank gần nhất, chặn 1 lần / 60 giây). Bài cũ mặc định `muc=0`.

`ly_do_to_de`: lý do từng phương án khoá theo dấu vân nội dung câu trên tờ đề.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f7a1c9d2e5'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9b1d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('de_cuoi_ky', sa.Column('muc', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('de_cuoi_ky', sa.Column('bai_lam_tb_id', sa.Text(), nullable=True))
    op.add_column('de_cuoi_ky', sa.Column('chi_tiet_json', sa.Text(), nullable=True))
    op.add_column('de_cuoi_ky', sa.Column('dap_an_mo', sa.Boolean(), nullable=False,
                                          server_default=sa.text('false')))
    op.add_column('de_cuoi_ky', sa.Column('het_han_dap_an', sa.Boolean(), nullable=False,
                                          server_default=sa.text('false')))
    op.add_column('de_cuoi_ky', sa.Column('kiem_luc', sa.DateTime(), nullable=True))

    op.create_table(
        'ly_do_to_de',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('noi_dung_hash', sa.String(length=64), nullable=False),
        sa.Column('option_key', sa.String(length=16), nullable=False),
        sa.Column('noi_dung', sa.Text(), nullable=False, server_default=''),
        sa.Column('nguon', sa.String(length=16), nullable=False, server_default='ai'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('noi_dung_hash', 'option_key'),
    )
    op.create_index(op.f('ix_ly_do_to_de_noi_dung_hash'), 'ly_do_to_de', ['noi_dung_hash'])


def downgrade() -> None:
    op.drop_index(op.f('ix_ly_do_to_de_noi_dung_hash'), table_name='ly_do_to_de')
    op.drop_table('ly_do_to_de')
    for c in ('kiem_luc', 'het_han_dap_an', 'dap_an_mo', 'chi_tiet_json', 'bai_lam_tb_id', 'muc'):
        op.drop_column('de_cuoi_ky', c)
