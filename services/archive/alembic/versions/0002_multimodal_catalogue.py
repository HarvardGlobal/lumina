"""Add the multimodal Archive catalogue and lineage tables.

Revision ID: 0002_multimodal_catalogue
Revises: 0001_archive_record
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_multimodal_catalogue"
down_revision = "0001_archive_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_batch",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_system", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="received", nullable=False),
        sa.Column("record_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_cursor", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("pipeline_version", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('received', 'running', 'completed', 'failed')", name="ck_ingestion_batch_status"),
    )
    op.create_index("ix_ingestion_batch_source_system", "ingestion_batch", ["source_system"])

    op.create_table(
        "archive_object",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("original_filename", sa.String(length=1024), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("compression", sa.String(length=64), nullable=True),
        sa.Column("source_format", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("storage_backend", sa.String(length=64), server_default="filesystem", nullable=False),
        sa.Column("encryption_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_uri"),
    )
    op.create_index("ix_archive_object_sha256", "archive_object", ["sha256"])

    op.create_table(
        "archive_dataset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lumina_person_id", sa.Uuid(), nullable=True),
        sa.Column("source_system", sa.String(length=255), nullable=False),
        sa.Column("modality", sa.String(length=128), nullable=False),
        sa.Column("dataset_type", sa.String(length=128), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=True),
        sa.Column("quality_status", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("ingestion_batch_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["ingestion_batch.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_uri"),
    )
    for name, columns in (
        ("ix_archive_dataset_lumina_person_id", ["lumina_person_id"]),
        ("ix_archive_dataset_source_system", ["source_system"]),
        ("ix_archive_dataset_modality", ["modality"]),
        ("ix_archive_dataset_metric", ["metric"]),
        ("ix_archive_dataset_start_time", ["start_time"]),
        ("ix_archive_dataset_end_time", ["end_time"]),
    ):
        op.create_index(name, "archive_dataset", columns)

    op.alter_column("archive_record", "patient_id", existing_type=sa.String(length=255), nullable=True)
    op.alter_column(
        "archive_record",
        "raw_payload",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(),
        postgresql_using="raw_payload::jsonb",
        nullable=True,
    )
    op.alter_column(
        "archive_record",
        "normalized_payload",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(),
        postgresql_using="normalized_payload::jsonb",
        nullable=True,
    )
    op.add_column("archive_record", sa.Column("lumina_person_id", sa.Uuid(), nullable=True))
    op.add_column("archive_record", sa.Column("source_subject_id", sa.String(length=255), nullable=True))
    op.add_column("archive_record", sa.Column("identity_status", sa.String(length=32), server_default="unresolved", nullable=False))
    op.add_column("archive_record", sa.Column("storage_type", sa.String(length=32), server_default="inline_json", nullable=False))
    op.add_column("archive_record", sa.Column("content_type", sa.String(length=255), nullable=True))
    op.add_column("archive_record", sa.Column("format", sa.String(length=128), nullable=True))
    op.add_column("archive_record", sa.Column("object_id", sa.Uuid(), nullable=True))
    op.add_column("archive_record", sa.Column("dataset_id", sa.Uuid(), nullable=True))
    op.add_column("archive_record", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.add_column("archive_record", sa.Column("supersedes_record_id", sa.Uuid(), nullable=True))
    op.add_column("archive_record", sa.Column("ingestion_batch_id", sa.Uuid(), nullable=True))
    op.add_column("archive_record", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("archive_record", sa.Column("status", sa.String(length=32), server_default="received", nullable=False))
    op.create_foreign_key("fk_archive_record_object", "archive_record", "archive_object", ["object_id"], ["id"])
    op.create_foreign_key("fk_archive_record_dataset", "archive_record", "archive_dataset", ["dataset_id"], ["id"])
    op.create_foreign_key("fk_archive_record_supersedes", "archive_record", "archive_record", ["supersedes_record_id"], ["id"])
    op.create_foreign_key("fk_archive_record_batch", "archive_record", "ingestion_batch", ["ingestion_batch_id"], ["id"])
    op.create_index("ix_archive_record_lumina_person_id", "archive_record", ["lumina_person_id"])
    op.create_index("ix_archive_record_source_subject_id", "archive_record", ["source_subject_id"])
    op.create_index("ix_archive_record_source_identifier", "archive_record", ["source_system", "source_record_id"])
    op.create_index("ix_archive_record_idempotency", "archive_record", ["source_system", "idempotency_key"])
    op.create_check_constraint(
        "ck_archive_record_storage_type",
        "archive_record",
        "storage_type IN ('inline_json', 'object', 'parquet', 'external_reference')",
    )
    op.create_check_constraint(
        "ck_archive_record_status",
        "archive_record",
        "status IN ('received', 'validated', 'quarantined', 'archived', 'failed')",
    )
    op.create_check_constraint(
        "ck_archive_record_identity_status",
        "archive_record",
        "identity_status IN ('unresolved', 'linked', 'verified', 'disputed')",
    )

    op.create_table(
        "archive_provenance_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("archive_record_id", sa.Uuid(), nullable=True),
        sa.Column("archive_object_id", sa.Uuid(), nullable=True),
        sa.Column("archive_dataset_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_service", sa.String(length=128), server_default="lumina-archive", nullable=False),
        sa.Column("source_system", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("pipeline_name", sa.String(length=128), nullable=True),
        sa.Column("pipeline_version", sa.String(length=64), nullable=True),
        sa.Column("mapping_version", sa.String(length=64), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["archive_record_id"], ["archive_record.id"]),
        sa.ForeignKeyConstraint(["archive_object_id"], ["archive_object.id"]),
        sa.ForeignKeyConstraint(["archive_dataset_id"], ["archive_dataset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("ix_archive_provenance_event_record", "archive_record_id"),
        ("ix_archive_provenance_event_object", "archive_object_id"),
        ("ix_archive_provenance_event_dataset", "archive_dataset_id"),
        ("ix_archive_provenance_event_type", "event_type"),
    ):
        op.create_index(name, "archive_provenance_event", [column])

    op.create_table(
        "archive_promotion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("archive_record_id", sa.Uuid(), nullable=True),
        sa.Column("archive_dataset_id", sa.Uuid(), nullable=True),
        sa.Column("target_system", sa.String(length=64), server_default="promop", nullable=False),
        sa.Column("target_domain", sa.String(length=128), nullable=True),
        sa.Column("target_table", sa.String(length=128), nullable=True),
        sa.Column("target_record_id", sa.String(length=255), nullable=True),
        sa.Column("mapping_version", sa.String(length=64), nullable=True),
        sa.Column("transform_version", sa.String(length=64), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["archive_record_id"], ["archive_record.id"]),
        sa.ForeignKeyConstraint(["archive_dataset_id"], ["archive_dataset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_archive_promotion_record", "archive_promotion", ["archive_record_id"])
    op.create_index("ix_archive_promotion_dataset", "archive_promotion", ["archive_dataset_id"])


def downgrade() -> None:
    op.drop_table("archive_promotion")
    op.drop_table("archive_provenance_event")
    op.drop_constraint("ck_archive_record_identity_status", "archive_record", type_="check")
    op.drop_constraint("ck_archive_record_status", "archive_record", type_="check")
    op.drop_constraint("ck_archive_record_storage_type", "archive_record", type_="check")
    op.drop_index("ix_archive_record_idempotency", table_name="archive_record")
    op.drop_index("ix_archive_record_source_identifier", table_name="archive_record")
    op.drop_index("ix_archive_record_source_subject_id", table_name="archive_record")
    op.drop_index("ix_archive_record_lumina_person_id", table_name="archive_record")
    for name in ("fk_archive_record_batch", "fk_archive_record_supersedes", "fk_archive_record_dataset", "fk_archive_record_object"):
        op.drop_constraint(name, "archive_record", type_="foreignkey")
    for name in ("status", "idempotency_key", "ingestion_batch_id", "supersedes_record_id", "content_sha256", "dataset_id", "object_id", "format", "content_type", "storage_type", "identity_status", "source_subject_id", "lumina_person_id"):
        op.drop_column("archive_record", name)
    op.alter_column("archive_record", "normalized_payload", existing_type=postgresql.JSONB(), type_=sa.JSON(), postgresql_using="normalized_payload::json", nullable=True)
    op.alter_column("archive_record", "raw_payload", existing_type=postgresql.JSONB(), type_=sa.JSON(), postgresql_using="raw_payload::json", nullable=False)
    op.alter_column("archive_record", "patient_id", existing_type=sa.String(length=255), nullable=False)
    op.drop_table("archive_dataset")
    op.drop_table("archive_object")
    op.drop_table("ingestion_batch")
