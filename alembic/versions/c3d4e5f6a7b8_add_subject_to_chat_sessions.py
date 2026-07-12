"""add subject to chat_sessions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-12 09:00:00.000000

Lịch sử chat theo môn học (đa môn): mỗi phiên gắn 1 môn để lọc sidebar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='toan' để các phiên cũ (chỉ có Toán) được gán đúng môn.
    op.add_column('chat_sessions', sa.Column('subject', sa.String(), nullable=False, server_default='toan'))
    op.create_index(op.f('ix_chat_sessions_subject'), 'chat_sessions', ['subject'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_sessions_subject'), table_name='chat_sessions')
    op.drop_column('chat_sessions', 'subject')
