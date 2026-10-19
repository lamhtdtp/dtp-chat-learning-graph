"""de_cuoi_ky.attempt_id — nối đề cuối kỳ với lần nộp, để học sinh xoá hẳn được

Revision ID: a1d5e2f3b4c6
Revises: 9c4e1a7b2d30
Create Date: 2026-10-19 10:00:00.000000

Trước đây đề (`de_cuoi_ky`) và lần nộp (`quiz_attempts`, nguon="cuoi_ky") không
có liên kết nào — xoá đề không biết phải xoá lần nộp nào, thống kê YCCĐ sẽ còn
đếm bài học sinh đã xoá.

Nối dữ liệu cũ: mỗi lần nộp tạo ĐÚNG một attempt trong cùng giao dịch, nên với
từng học sinh, đề đã nộp xếp theo thời điểm nộp khớp 1-1 với attempt cuoi_ky xếp
theo id. Học sinh nào số lượng hai bên lệch nhau thì BỎ QUA (không đoán) — các
đề đó vẫn xoá được, chỉ là lần nộp cũ còn lại trong thống kê.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1d5e2f3b4c6'
down_revision: Union[str, Sequence[str], None] = '9c4e1a7b2d30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('de_cuoi_ky', sa.Column('attempt_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_de_cuoi_ky_attempt_id', 'de_cuoi_ky', 'quiz_attempts',
                          ['attempt_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_de_cuoi_ky_attempt_id'), 'de_cuoi_ky', ['attempt_id'], unique=False)

    op.execute("""
        WITH de AS (
            SELECT id, user_id,
                   row_number() OVER (PARTITION BY user_id ORDER BY nop_luc, created_at, id) AS n,
                   count(*)     OVER (PARTITION BY user_id) AS tong
            FROM de_cuoi_ky WHERE nop_luc IS NOT NULL
        ), at AS (
            SELECT id, user_id,
                   row_number() OVER (PARTITION BY user_id ORDER BY id) AS n,
                   count(*)     OVER (PARTITION BY user_id) AS tong
            FROM quiz_attempts WHERE nguon = 'cuoi_ky'
        )
        UPDATE de_cuoi_ky d SET attempt_id = at.id
        FROM de JOIN at ON at.user_id = de.user_id AND at.n = de.n AND at.tong = de.tong
        WHERE d.id = de.id
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_de_cuoi_ky_attempt_id'), table_name='de_cuoi_ky')
    op.drop_constraint('fk_de_cuoi_ky_attempt_id', 'de_cuoi_ky', type_='foreignkey')
    op.drop_column('de_cuoi_ky', 'attempt_id')
