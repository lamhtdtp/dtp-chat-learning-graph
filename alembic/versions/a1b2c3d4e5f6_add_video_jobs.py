"""add video_jobs

Revision ID: a1b2c3d4e5f6
Revises: dfc009d02a70
Create Date: 2026-07-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'dfc009d02a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'video_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('concept_key', sa.String(), nullable=False),
        sa.Column('sgk_version', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('video_url', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('duration_sec', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('concept_key', 'sgk_version'),
    )
    op.create_index(op.f('ix_video_jobs_concept_key'), 'video_jobs', ['concept_key'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_video_jobs_concept_key'), table_name='video_jobs')
    op.drop_table('video_jobs')
