# ADR 0001: Preserve three-repository boundaries

## Status

Accepted

## Context

LUMINA Core, LUMINA Wearables, and PRomop have distinct ownership and release
cadences.

## Decision

Use sibling `lumina`, `lumina-wearables`, and `promop` repositories. Only the
first two are LUMINA repositories; PRomop remains an external dependency.

## Consequences

Local Compose can build the siblings for development. Production must instead
use pinned component images. LUMINA does not duplicate OMOP or PatientRecord.
