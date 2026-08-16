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

Core only performs stable connectivity checks until an approved promotion
contract is implemented. No `lumina-omop` or `lumina-patientrecord` project is
created.
