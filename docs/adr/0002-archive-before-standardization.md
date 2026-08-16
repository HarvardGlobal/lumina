# ADR 0002: Archive before standardization

## Status

Accepted

## Context

Source data can be incomplete, unmapped, or later remapped. Losing the source
representation would prevent reprocessing and provenance review.

## Decision

Preserve the source representation in the LUMINA Archive before or alongside
any standardization. Promotion is selective and must retain Archive lineage.

## Consequences

The Archive has its own source-preserving schema and API. Unmapped source data
remains accessible without implying it is an OMOP interpretation.
