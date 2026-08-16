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

Only a validated, eligible Archive record may be promoted. A promotion must
retain the Archive UUID as lineage in the approved PRomop integration contract.
Unmapped, rejected, or high-frequency source data remains Archive-only; it is
not deleted or silently substituted.

No final clinical terminology mapping is defined by this document. Mapping,
eligibility criteria, and target PRomop interface must be approved and covered
by an integration test before Archive-to-OMOP promotion is enabled.

## Large payloads

The initial implementation stores JSON payloads in PostgreSQL. A future
`raw_payload_uri` extension may point at object storage while this record keeps
the provenance and identifier. Object-storage behavior is intentionally not
implemented in the first milestone.
