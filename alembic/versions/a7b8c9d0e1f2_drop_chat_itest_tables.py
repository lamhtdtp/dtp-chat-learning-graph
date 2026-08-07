"""drop chat + itest tables (P5: bỏ hẳn chat/RAG + ngân hàng Itest)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-06 12:00:00.000000

Gỡ tính năng chat/RAG và gợi ý Itest. Các bảng messages, chat_sessions,
itest_questions, itest_topic_map không còn model/endpoint nào dùng.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # messages tham chiếu chat_sessions -> drop con trước.
    op.drop_table('messages')
    op.drop_table('chat_sessions')
    op.drop_table('itest_topic_map')
    op.drop_table('itest_questions')


def downgrade() -> None:
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject', sa.String(), nullable=False, server_default='toan'),
        sa.Column('title', sa.String(), nullable=False, server_default='Cuộc trò chuyện'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_active', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_chat_sessions_user_id', 'chat_sessions', ['user_id'])
    op.create_index('ix_chat_sessions_subject', 'chat_sessions', ['subject'])
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('chat_sessions.id'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('citations_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_messages_session_id', 'messages', ['session_id'])
    op.create_table(
        'itest_questions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('itest_id', sa.String(), nullable=False),
        sa.Column('tag_goc', sa.String(), nullable=False),
        sa.Column('question_type', sa.String(), nullable=False, server_default='MC'),
        sa.Column('noi_dung', sa.Text(), nullable=False),
        sa.Column('options_json', sa.Text(), nullable=True),
        sa.Column('dap_an', sa.Text(), nullable=True),
        sa.Column('loi_giai', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_itest_questions_itest_id', 'itest_questions', ['itest_id'], unique=True)
    op.create_index('ix_itest_questions_tag_goc', 'itest_questions', ['tag_goc'])
    op.create_index('ix_itest_questions_content_hash', 'itest_questions', ['content_hash'])
    op.create_table(
        'itest_topic_map',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('itest_tag', sa.String(), nullable=False),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('curriculum_topics.id'), nullable=True),
        sa.Column('muc_do', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='cho_duyet'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_itest_topic_map_itest_tag', 'itest_topic_map', ['itest_tag'], unique=True)
