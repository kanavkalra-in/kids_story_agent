"""add_rejection_reason_to_story_reviews

Revision ID: 778e9781079a
Revises: a3b7c9d1e2f4
Create Date: 2026-02-16 20:45:30.328921

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '778e9781079a'
down_revision: Union[str, None] = 'a3b7c9d1e2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add rejection_reason column to story_reviews table
    op.add_column('story_reviews', sa.Column('rejection_reason', sa.String(50), nullable=True))


def downgrade() -> None:
    # Remove rejection_reason column
    op.drop_column('story_reviews', 'rejection_reason')
