# Wearable data identity, versions, and lineage

## Status today

Archive already has the building blocks for wearable lineage: immutable raw
objects with SHA-256, a normalised Parquet dataset catalogue, source and LUMINA
identity fields, a mapping version, schema version, ingestion batch, provenance
events, and an explicit record supersession link.

LUMINA Wearables does **not** call Archive yet. Its current endpoint is a
read-only preview of Open Wearables recovery data. This document is the
contract the Archive integration must implement before patient data is sent.

## The three distinct versions

Do not call every version simply “the wearable version.” Each ingestion must
retain these separate values:

| What changed | Example | Where it belongs | Why |
| --- | --- | --- | --- |
| Acquisition software | Open Wearables `0.7.0`, Git `cb3ad1f…` | Raw-object metadata and ingestion provenance | Explains the source API behaviour and provider adapter used. |
| Source-device context | provider `garmin`, model/type, pseudonymous device ID, firmware if supplied | Raw-object metadata and every normalised observation | A person can change device; the same device can have multiple collection periods. It is not a person identifier. |
| LUMINA interpretation | Wearables Git `5d9fc7b…`, mapping `wearable-mapping/0.1.1`, schema `1.1.0` | Dataset `mapping_version`, `schema_version`, provenance event | Allows a mapping correction to create a new derived dataset without changing source evidence. |
| OMOP vocabulary | Athena release identifier plus the resolved local OMOP `concept_id` | Approved export and promotion receipt | Explains exactly which standard concept was used if a vocabulary release changes. |

The content SHA-256 identifies a particular immutable payload, while the
source record identifier and retrieval window identify what the provider says
that payload represents. Neither is a clinical identity.

## Required archive flow

```text
Device/provider payload
  -> immutable raw Archive object
  -> normalised, versioned Archive dataset
  -> approved daily metric and LOINC code
  -> local OMOP concept from a pinned Athena vocabulary release
  -> PRomop receipt / OMOP identifiers
```

1. Preserve the exact Open Wearables API response and request context as an
   encrypted raw Archive object. Record Open Wearables release/SHA, API path,
   retrieval window, provider, device metadata, source user ID, and content
   hash. Never rewrite it.
2. Create a normalised wearable dataset derived from that object. Each row
   retains provider, device identifier, source metric, source unit, timestamp,
   value, source-record identifier, schema version, and mapping version.
3. Link a source subject to a LUMINA person only through an explicit,
   authorised identity process. An Open Wearables UUID or device ID must never
   be guessed to be a PRomop person.
4. On a source correction, retain the earlier object and create a replacement
   record with `supersedes_record_id`. On a LUMINA mapping correction, retain
   the same raw object and create a new derived dataset/provenance event with a
   new mapping version. Never overwrite old measurements.
5. Promote only an approved, traceable daily derived metric. Resolve its
   approved LOINC code against PRomop's local OMOP vocabulary loaded from a
   pinned Athena release; do not call Athena as a live ingestion service.
   Store the vocabulary release, resolved OMOP concept ID, target receipt, and
   OMOP identifiers as a promotion event. Raw heart-rate samples remain Archive
   data, not one OMOP measurement per sample.

## Device-linking rule

Device data has two independent relationships:

```text
provider subject ── explicit identity link ──> LUMINA person
provider device  ── observed during time range ──> raw/dataset records
```

The device relation is temporal, not permanent ownership. Store a provider
device ID only when supplied, treat it as potentially sensitive pseudonymous
data, and retain model/type/firmware in the raw provenance. A device model is
useful for quality review; it must not replace the provider’s source metric or
make a medical claim about measurement equivalence.

## Implementation prerequisite

Before enabling Archive writes, add and test a dedicated authenticated
Wearables-to-Archive contract that carries the immutable raw response plus the
normalised observations and their linkage. The existing generic wearable
dataset endpoint is not sufficient by itself to prove preservation of the
original upstream response. The contract must specify authentication,
idempotency, source-identity link authorisation, raw retention/deletion,
device metadata handling, and correction/replay behaviour.
