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

## Security and deployment modes

The local object backend is a Docker named volume mounted only into the Archive
container; it has no public bucket or direct host HTTP endpoint. It is for
development and synthetic data only. Raw object download and all Archive API
routes (including catalogue, metadata, patient search, lineage, and promotion)
require a bearer credential whenever `ARCHIVE_BEARER_TOKEN` is set:

```http
Authorization: Bearer <token>
```

An empty token is permitted only for local development. Production refuses to
start without a 32+ character token, a request-size limit, and a positive
rate-limit backstop. It also disables Archive OpenAPI/docs and adds `no-store`
response headers. The bearer token is a narrow service credential, not a user
authorization system; it must never be exposed to a browser.

Production supports a private S3-compatible `ObjectStore` using opaque UUID
keys and checksums. It requires an approved private bucket, `aws:kms`
server-side encryption, and a named KMS key. Credentials use workload identity
through the AWS provider chain. Configure ingress OIDC/RBAC, global rate
limits, TLS, logging/redaction, backup/restore, retention/object lock, and
consent/identity policy outside this service, as documented in the README.
Do not place credentials or API tokens in stored payload metadata. This
implementation does not claim HIPAA or other regulatory compliance.
