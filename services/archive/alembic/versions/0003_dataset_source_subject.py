"""Add source subject identity to the dataset catalogue.

Revision ID: 0003_dataset_source_subject
Revises: 0002_multimodal_catalogue
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_dataset_source_subject"
down_revision = "0002_multimodal_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("archive_dataset", sa.Column("source_subject_id", sa.String(length=255), nullable=True))
    op.create_index("ix_archive_dataset_source_subject_id", "archive_dataset", ["source_subject_id"])


def downgrade() -> None:
    op.drop_index("ix_archive_dataset_source_subject_id", table_name="archive_dataset")
    op.drop_column("archive_dataset", "source_subject_id")
