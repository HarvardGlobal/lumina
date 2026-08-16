# ADR 0003: Reuse PRomop for OMOP and PatientRecord

## Status

Accepted

## Context

PRomop already provides OMOP CDM 5.4, FHIR ingestion, PostgreSQL migrations,
REST APIs, and the PatientRecord projection.

## Decision

Integrate with PRomop through a small LUMINA-owned adapter. PRomop remains the
owner of its models, APIs, migrations, OMOP representation, and PatientRecord.

## Consequences

Core provides a narrow, authenticated adapter for preserved FHIR R4 Bundles.
It forwards a caller-selected existing PRomop Person ID to PRomop's FHIR sync
API, stores the returned OMOP identifiers as Archive lineage, and does not
write PRomop's database directly. Other Archive data, including raw and
high-frequency wearable data, remains Archive-only until it has an approved
versioned transform and integration test. No `lumina-omop` or
`lumina-patientrecord` project is created.
