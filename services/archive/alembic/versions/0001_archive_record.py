"""Create the LUMINA source-preserving archive record table.

Revision ID: 0001_archive_record
Revises:
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_archive_record"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archive_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.String(length=255), nullable=False),
        sa.Column("source_system", sa.String(length=255), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("record_type", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("normalized_payload", sa.JSON(), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=True),
        sa.Column("quality_status", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_archive_record_patient_id", "archive_record", ["patient_id"])
    op.create_index("ix_archive_record_source_system", "archive_record", ["source_system"])


def downgrade() -> None:
    op.drop_index("ix_archive_record_source_system", table_name="archive_record")
    op.drop_index("ix_archive_record_patient_id", table_name="archive_record")
    op.drop_table("archive_record")
