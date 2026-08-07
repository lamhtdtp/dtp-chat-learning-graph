"""add curriculum_topics.hoc_ky (đa học kỳ)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-07 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('curriculum_topics', sa.Column('hoc_ky', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('curriculum_topics', 'hoc_ky')
