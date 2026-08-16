# LUMINA Archive storage and lineage

## Purpose and boundaries

The Archive is LUMINA's authoritative record of what was received. It preserves
source information before reduction or standardization. It does not own an OMOP
model, terminology mapping, clinical transformation, or PatientRecord.

```text
Source bytes -> Archive object store -> Archive catalogue / provenance
                       |
                       +-> normalized Parquet
                                      |
                         Archive-only pending approved aggregation
                                      v

 Stored FHIR R4 Bundle -> explicit PRomop person -> PRomop FHIR sync
                                                     |
                                                    OMOP + PatientRecord
```

PRomop is the standardized interpretation layer. PatientRecord is derived from
OMOP and never replaces the received source object or Archive dataset.

## Which storage is used

| Source material | Storage | Catalogue entry | Example |
| --- | --- | --- | --- |
| Small structured record | PostgreSQL JSONB | `archive_record` | small survey response |
| Exact API/FHIR payload | private object storage | `archive_object` + `archive_record` | FHIR Bundle, provider JSON |
| High-volume structured data | Parquet with ZSTD | `archive_dataset` + linked record/object | minute heart rate, sleep epochs |
| Very high-frequency/native binary | private object storage | `archive_object` + `archive_record` | ECG, DICOM, genomics, documents |
| PRomop FHIR synchronization result | `archive_promotion` JSON lineage | `archive_promotion` | FHIR Bundle promoted to OMOP |

PostgreSQL is the control plane: metadata, identity references, checksums,
provenance, catalogue searches, and promotion lineage. It is not the
store for one row per high-frequency observation.

## Current ingestion paths

The backwards-compatible JSON endpoint remains available:

```text
POST /api/v1/archive/records
```

It accepts a small JSON payload and creates an `inline_json` Archive record.
`patient_id` remains required on this legacy endpoint and is also recorded as
`source_subject_id`. It is not treated as a resolved LUMINA identity.

New source bytes are accepted through:

```text
POST /api/v1/archive/objects
POST /api/v1/archive/fhir
POST /api/v1/archive/datasets/wearables
```

`/objects` preserves arbitrary bytes exactly. `/fhir` preserves original FHIR
JSON bytes first, calculates SHA-256, and indexes only non-transformative
metadata: FHIR version, Bundle type, resource types, profiles, and an available
source Patient identifier. Ingestion itself does not convert FHIR into OMOP.

The wearable endpoint stores the exact submitted provider JSON as an
`archive_object`, writes normalized observations to a new immutable Parquet
file using ZSTD compression, and creates one linked Archive record and dataset
catalogue entry. A 1,440-minute day is therefore 1,440 Parquet rows, not 1,440
PostgreSQL `archive_record` rows.

## Identity

Every new record or dataset can have both:

- `lumina_person_id`: an optional resolved LUMINA UUID;
- `source_system` + `source_subject_id`: the source's own identity.

`lumina_person_id` may be absent. `identity_status` records `unresolved`,
`linked`, `verified`, or `disputed`; Archive does not perform fuzzy matching.

## Immutability, idempotency, and corrections

There are no public update or delete endpoints for Archive records, objects, or
datasets. Object and Parquet paths are opaque UUID paths and filesystem writes
refuse to overwrite an existing path. The local backend's `delete` operation is
only an internal lifecycle hook; it has no HTTP endpoint.

Retries are deduplicated by `source_system` plus a stable `source_record_id`,
or by `Idempotency-Key`. Raw objects also carry SHA-256. A retry with the same
logical identifier but different content returns a conflict instead of silently
overwriting history. Equal measurements are not used as a duplicate rule.

Corrections create a new record with `supersedes_record_id`; the earlier record
remains readable. Production WORM/object-lock retention is deployment-specific
and is not supplied by the local Docker filesystem backend.

## Provenance and promotion lineage

`archive_provenance_event` records receipt, storage, validation,
normalization, sensitive reads, promotion, and supersession. `archive_promotion`
records promotion target, result IDs/details, mapping version, transform
version, status, and error.

The enabled promotion endpoint is:

```text
POST /api/v1/archive/records/{record_id}/promote/promop
```

It accepts `{ "promop_person_id": <positive integer> }` and only permits a
preserved `fhir-json` Bundle with a source object. Archive reads the preserved
bytes and calls PRomop's authenticated FHIR sync API with the explicitly chosen
person. PRomop—not Archive—performs the FHIR-to-OMOP mapping and returns its
created OMOP identifiers. Archive stores that response as immutable lineage.

The same record, PRomop person, mapping version, and transform version is
idempotent after success: Archive returns the existing promotion without a
second PRomop call. A failed request remains a failed promotion event and does
not delete or alter the source object.

Generic JSON, raw objects, and wearable Parquet datasets have no promotion
endpoint. They stay Archive-only unless an approved, versioned aggregation and
PRomop mapping is added with an integration test; high-frequency samples must
not be mapped one-for-one into OMOP.

Use `GET /api/v1/archive/records/{id}/lineage` to inspect the linked source
record, raw object, normalized dataset, events, and known promotions.
Dataset catalogue queries are available at `/api/v1/archive/datasets` with
person, source, modality, metric, and time-range filters.

## Security and local deployment

The local object backend is a Docker named volume mounted only into the Archive
container; it has no public bucket or direct host HTTP endpoint. Raw object
download and new object/FHIR/dataset ingestion go through Archive service
endpoints. Set `ARCHIVE_BEARER_TOKEN` in `.env` to require:

```http
Authorization: Bearer <token>
```

for those protected paths. An empty token is permitted only for local
development. The current hook is deliberately small; organization-wide RBAC,
consent, service identity, key management, retention schedules, and production
object-lock policy belong to the broader LUMINA authorization/deployment layer.
This implementation does not claim HIPAA compliance.

For production, replace the filesystem `ObjectStore` backend with a private
service such as MinIO/S3 while retaining opaque UUID keys and checksum/catalogue
semantics. Do not place credentials or API tokens in stored payload metadata.
