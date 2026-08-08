"""add topic_content.ai_soan; nguon -> Text

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-08 09:00:00.000000

Tách cờ "nội dung do AI soạn" ra khỏi cột `nguon`. Trước đây CMS suy cờ này bằng
`"AI" in c.nguon` — dò chuỗi con, nên trích đoạn SGK viết hoa chứa "HAI" (rất hay
gặp trong Toán: "CHỈ CÓ HAI ƯỚC") bị gắn nhãn AI oan, và ngược lại sửa `nguon`
thành tư liệu thật thì mất nhãn.

Backfill giữ nguyên hành vi cũ cho dữ liệu đang có: bản ghi nào mang ĐÚNG một
trong các chuỗi đánh dấu mà code cũ tự ghi (CMS "Nạp sách bằng AI" và script
app.seed_all_lessons) thì ai_soan = true, rồi xoá chuỗi đó khỏi `nguon` để ô tư
liệu trở lại đúng nghĩa. KHÔNG backfill theo LIKE '%AI%' — làm vậy là bê nguyên
lỗi dương tính giả sang cột mới.

`nguon` cũng đổi sang Text: nó chứa trích đoạn SGK dán vào, không phải nhãn ngắn.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mọi chuỗi đánh dấu mà code cũ từng tự ghi vào `nguon`. Khớp CHÍNH XÁC, không
# LIKE — tư liệu chuyên gia dán vào cũng nằm ở cột này.
_DAU_AI = ('AI soạn nháp (CMS ingest)', 'AI soạn nháp (app.seed_all_lessons)')


def upgrade() -> None:
    op.add_column(
        'topic_content',
        sa.Column('ai_soan', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('topic_content', 'nguon', type_=sa.Text(), existing_nullable=True)
    op.execute(
        sa.text("UPDATE topic_content SET ai_soan = true, nguon = NULL WHERE nguon IN :dau")
        .bindparams(sa.bindparam('dau', value=_DAU_AI, expanding=True))
    )


def downgrade() -> None:
    # Trả lại chuỗi đánh dấu để CMS bản cũ (dò "AI" in nguon) vẫn nhận ra. Không
    # khôi phục được ĐÚNG nguồn gốc (CMS hay script) — gộp về một nhãn.
    op.execute(
        sa.text("UPDATE topic_content SET nguon = :dau WHERE ai_soan = true AND nguon IS NULL")
        .bindparams(dau=_DAU_AI[0])
    )
    op.drop_column('topic_content', 'ai_soan')
    op.alter_column('topic_content', 'nguon', type_=sa.String(), existing_nullable=True)
