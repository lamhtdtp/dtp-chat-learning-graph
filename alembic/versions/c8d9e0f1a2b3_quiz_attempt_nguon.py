"""quiz_attempts.nguon — tách lượt Kiểm tra nhanh khỏi mảnh đề Ôn tập

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quiz_attempts",
                  sa.Column("nguon", sa.String(), nullable=False, server_default="nhanh"))
    op.create_index(op.f("ix_quiz_attempts_nguon"), "quiz_attempts", ["nguon"])


def downgrade() -> None:
    op.drop_index(op.f("ix_quiz_attempts_nguon"), table_name="quiz_attempts")
    op.drop_column("quiz_attempts", "nguon")
