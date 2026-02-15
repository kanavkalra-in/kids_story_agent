"""add_generate_images_and_videos_columns

Revision ID: 2c01c319aca4
Revises: 
Create Date: 2026-02-15 16:13:05.874049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c01c319aca4'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add generate_images column with default True
    op.add_column('story_jobs', sa.Column('generate_images', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add generate_videos column with default False
    op.add_column('story_jobs', sa.Column('generate_videos', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove the columns
    op.drop_column('story_jobs', 'generate_videos')
    op.drop_column('story_jobs', 'generate_images')
