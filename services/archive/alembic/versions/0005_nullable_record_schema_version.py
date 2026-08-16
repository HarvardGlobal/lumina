"""Allow object-backed Archive records without an inline schema version.

Revision ID: 0005_nullable_schema_version
Revises: 0004_promotion_target_details
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_nullable_schema_version"
down_revision = "0004_promotion_target_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("archive_record", "schema_version", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    op.alter_column("archive_record", "schema_version", existing_type=sa.String(length=64), nullable=False)
