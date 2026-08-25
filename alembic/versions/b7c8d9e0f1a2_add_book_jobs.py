"""add book_jobs — theo dõi tiến độ nạp sách theo TRANG (REQ §2.4)

Revision ID: b7c8d9e0f1a2
Revises: e8f9a0b1c2d3
Create Date: 2026-08-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "book_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mon", sa.String(), nullable=False),
        sa.Column("khoi", sa.String(), nullable=False),
        sa.Column("tap", sa.Integer(), nullable=False),
        sa.Column("sach", sa.String(), nullable=False),
        sa.Column("trang_thai", sa.String(), nullable=False, server_default="cho"),
        sa.Column("buoc", sa.String(), nullable=False, server_default="doc"),
        sa.Column("trang_ds_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trang_xong_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trang_loi_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trang_dang", sa.Integer(), nullable=True),
        sa.Column("trang_soat_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("so_trang_co_bai", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("so_doan", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loi", sa.Text(), nullable=True),
        sa.Column("nguoi_tao_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["nguoi_tao_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_book_jobs_trang_thai"), "book_jobs", ["trang_thai"])
    op.create_index(op.f("ix_book_jobs_created_at"), "book_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_book_jobs_created_at"), table_name="book_jobs")
    op.drop_index(op.f("ix_book_jobs_trang_thai"), table_name="book_jobs")
    op.drop_table("book_jobs")
