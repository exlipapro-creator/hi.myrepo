"""Add provider API key encryption fields

Revision ID: c3d4e5f6a7b8
Revises: b7e1f2a3c4d5
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = 'c3d4e5f6a7b8'
down_revision = 'b7e1f2a3c4d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add api_key_encrypted column for storing encrypted API keys
    op.add_column(
        'ai_providers',
        sa.Column('api_key_encrypted', sa.Text, nullable=True)
    )

    # Add configured_at to track when the provider was last configured
    op.add_column(
        'ai_providers',
        sa.Column('configured_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('ai_providers', 'configured_at')
    op.drop_column('ai_providers', 'api_key_encrypted')
