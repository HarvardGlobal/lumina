# LUMINA core setup

This repository is self-contained for local orchestration. `make setup` uses
the pinned entries in `config/components.yaml` to fetch PRomop and Wearables
into `.lumina/components/`; sibling repositories are no longer required.

The root Compose configuration owns orchestration only. PRomop remains the
owner of OMOP CDM 5.4, PatientRecord, and its Django migrations. Wearable
provider semantics remain in `lumina-wearables`. LUMINA owns the Archive and
the small integration adapters.

For a clean local start, copy `.env.example` to `.env`, review its local-only
values, then run `make setup`. Nix flakes pin the development command-line
toolchain; the component manifest pins source revisions. The command fetches
components first, then builds and starts services in Compose dependency order,
and checks health without modifying external source repositories.
