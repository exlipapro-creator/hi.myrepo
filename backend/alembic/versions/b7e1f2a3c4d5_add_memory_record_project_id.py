"""Add project_id to memory_records for tenancy isolation.

Revision ID: b7e1f2a3c4d5
Revises: 32d24d105027
Create Date: 2026-09-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7e1f2a3c4d5'
down_revision: Union[str, Sequence[str], None] = '32d24d105027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add project_id column to memory_records, backfill from incidents, then enforce NOT NULL."""

    # Step 1: Add project_id as nullable first
    with op.batch_alter_table('memory_records', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('project_id', sa.UUID(), nullable=True)
        )

    # Step 2: Backfill project_id from the linked incident's project
    op.execute("""
        UPDATE memory_records mr
        SET project_id = i.project_id
        FROM incidents i
        WHERE mr.incident_id = i.id
        AND mr.project_id IS NULL
    """)

    # Step 3: Add foreign key constraint
    with op.batch_alter_table('memory_records', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_memory_records_project_id',
            'projects',
            ['project_id'],
            ['id'],
        )

    # Step 4: Create index
    with op.batch_alter_table('memory_records', schema=None) as batch_op:
        batch_op.create_index(
            'idx_memory_records_project_id',
            ['project_id'],
            unique=False,
        )

    # Step 5: Enforce NOT NULL after backfill
    with op.batch_alter_table('memory_records', schema=None) as batch_op:
        batch_op.alter_column(
            'project_id',
            existing_type=sa.UUID(),
            nullable=False,
        )


def downgrade() -> None:
    """Remove project_id from memory_records."""
    with op.batch_alter_table('memory_records', schema=None) as batch_op:
        batch_op.drop_index('idx_memory_records_project_id')
        batch_op.drop_constraint('fk_memory_records_project_id', type_='foreignkey')
        batch_op.drop_column('project_id')
