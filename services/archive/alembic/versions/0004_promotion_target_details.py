"""Store structured PRomop promotion result lineage.

Revision ID: 0004_promotion_target_details
Revises: 0003_dataset_source_subject
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_promotion_target_details"
down_revision = "0003_dataset_source_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("archive_promotion", sa.Column("target_details", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("archive_promotion", "target_details")
