# Archive to PRomop contract

## Ownership

The LUMINA Archive is the source-preserving record of data received by
LUMINA. It assigns an immutable Archive UUID and retains the complete accepted
source payload, source identifiers, source system, received time, and available
source observation time.

PRomop is the standardized interpretation layer. It owns OMOP CDM 5.4 and the
derived PatientRecord projection. PatientRecord is regenerable from OMOP and
cannot become an independent source of truth.

## Promotion rules

Only a validated, eligible Archive record may be promoted. The enabled
integration is a preserved FHIR R4 Bundle submitted from Archive to PRomop's
authenticated FHIR sync API. The caller supplies an explicit existing
`promop_person_id`; Archive never performs identity resolution or fuzzy
matching. Archive records its UUID, the PRomop person, PRomop's returned OMOP
identifiers, mapping version, transform version, status, and error in
`archive_promotion` and provenance events.

PRomop owns the clinical terminology mapping and OMOP writes. Archive only
preserves and forwards the original Bundle, then persists the returned lineage;
it does not connect to or write PRomop's database. A successful request is
idempotent per Archive record, PRomop person, mapping version, and transform
version. Failures remain visible as failed lineage and leave the source intact.

Unmapped, rejected, high-frequency, or non-FHIR data remains Archive-only; it
is not deleted or silently substituted. Any additional promotion type requires
an approved versioned transform, defined eligibility, and a real PRomop
integration test before it is enabled.

## Large payloads

Raw source objects and high-volume normalized Parquet datasets remain in the
Archive. They must be reduced through an approved aggregation before any future
OMOP promotion; the Archive does not emit one OMOP row per wearable sample.
