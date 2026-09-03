"""Add recovery verification fields to incidents.

Revision ID: e7f8g9h0i1j2
Revises: d4e5f6a7b8c9
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8g9h0i1j2"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("recovery_success_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "incidents",
        sa.Column("recovery_verification_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "recovery_verification_started_at")
    op.drop_column("incidents", "recovery_success_count")
