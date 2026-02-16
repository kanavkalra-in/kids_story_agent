"""Add evaluation, guardrail, review tables and new job statuses

Revision ID: a3b7c9d1e2f4
Revises: 2c01c319aca4
Create Date: 2026-02-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3b7c9d1e2f4'
down_revision: Union[str, None] = '2c01c319aca4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Old and new enum values for JobStatus
OLD_STATUSES = ('pending', 'processing', 'completed', 'failed')
NEW_STATUSES = (
    'pending', 'processing', 'guardrail_check', 'pending_review',
    'approved', 'rejected', 'auto_rejected', 'published',
    'completed', 'failed',
)


def upgrade() -> None:
    # -- 1. Extend the JobStatus enum with new values --
    # PostgreSQL enums need ALTER TYPE to add values
    for status in NEW_STATUSES:
        if status not in OLD_STATUSES:
            op.execute(f"ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS '{status}'")

    # -- 2. Add parent_job_id column to story_jobs --
    op.add_column('story_jobs', sa.Column(
        'parent_job_id', postgresql.UUID(as_uuid=True),
        sa.ForeignKey('story_jobs.id'), nullable=True,
    ))

    # -- 3. Create story_evaluations table --
    op.create_table(
        'story_evaluations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('story_jobs.id'), nullable=False, unique=True),
        sa.Column('moral_score', sa.Float, nullable=False),
        sa.Column('theme_appropriateness', sa.Float, nullable=False),
        sa.Column('emotional_positivity', sa.Float, nullable=False),
        sa.Column('age_appropriateness', sa.Float, nullable=False),
        sa.Column('educational_value', sa.Float, nullable=False),
        sa.Column('overall_score', sa.Float, nullable=False),
        sa.Column('evaluation_summary', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # -- 4. Create guardrail_results table --
    op.create_table(
        'guardrail_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('story_jobs.id'), nullable=False),
        sa.Column('guardrail_name', sa.String(100), nullable=False),
        sa.Column('media_type', sa.String(20), nullable=False),
        sa.Column('media_index', sa.Integer, nullable=True),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('detail', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index('ix_guardrail_results_guardrail_name',
                    'guardrail_results', ['guardrail_name'])
    op.create_index('ix_guardrail_results_job_id',
                    'guardrail_results', ['job_id'])

    # -- 5. Create story_reviews table --
    op.create_table(
        'story_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('story_jobs.id'), nullable=False, unique=True),
        sa.Column('reviewer_id', sa.String(255), nullable=True),
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('guardrail_passed', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('overall_eval_score', sa.Float, nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('story_reviews')
    op.drop_table('guardrail_results')
    op.drop_table('story_evaluations')
    op.drop_column('story_jobs', 'parent_job_id')

    # Note: PostgreSQL does not support removing enum values.
    # A full enum replacement would be needed for a proper downgrade.
    # For simplicity, the extra enum values are left in place.
