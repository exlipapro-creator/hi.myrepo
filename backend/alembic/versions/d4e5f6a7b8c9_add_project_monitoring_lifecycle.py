"""Add project monitoring lifecycle fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add monitoring lifecycle fields to projects
    op.add_column(
        'projects',
        sa.Column('monitoring_status', sa.String(20), nullable=False, server_default='stopped')
    )
    op.add_column(
        'projects',
        sa.Column('monitoring_started_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'projects',
        sa.Column('monitoring_stopped_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add index for efficient monitoring queries
    op.create_index(
        'idx_projects_monitoring_status',
        'projects',
        ['monitoring_status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_projects_monitoring_status', table_name='projects')
    op.drop_column('projects', 'monitoring_stopped_at')
    op.drop_column('projects', 'monitoring_started_at')
    op.drop_column('projects', 'monitoring_status')
