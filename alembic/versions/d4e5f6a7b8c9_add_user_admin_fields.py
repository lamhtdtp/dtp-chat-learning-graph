"""add user admin fields (is_active, daily_limit_override)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-14 10:00:00.000000

Quản trị người dùng: khoá/mở tài khoản + hạn mức chat/ngày riêng cho từng user.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False,
                                     server_default=sa.text('true')))
    op.add_column('users', sa.Column('daily_limit_override', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'daily_limit_override')
    op.drop_column('users', 'is_active')
