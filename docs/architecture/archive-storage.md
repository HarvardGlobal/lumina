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
                         approved future promotion only
                                      v
                        PRomop: OMOP + PatientRecord
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
| Standardized clinical summary | PRomop, separately | future `archive_promotion` lineage | daily summary promoted to OMOP |

PostgreSQL is the control plane: metadata, identity references, checksums,
provenance, catalogue searches, and future promotion lineage. It is not the
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
source Patient identifier. It does not convert FHIR into OMOP.

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
normalization, sensitive reads, and supersession. `archive_promotion` reserves
the lineage needed for a future approved PRomop promotion—target table/record,
mapping version, transform version, status, and error—but Archive performs no
clinical mapping itself.

Use `GET /api/v1/archive/records/{id}/lineage` to inspect the linked source
record, raw object, normalized dataset, events, and known future promotions.
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
