# LUMINA

LUMINA orchestrates a source-preserving Archive, PRomop (OMOP CDM 5.4 and
PatientRecord), and the LUMINA wearable ingestion service. It is the entry
point for running the local development stack.

## Architecture

```text
Source -> LUMINA Archive -> selected standardized promotion -> PRomop
                                                       -> OMOP + PatientRecord
```

The Archive preserves the received source representation. PRomop is the
standardized, derived representation; PatientRecord is a regenerable
projection and is never a source of truth.

## Workspace

The core repository owns a versioned local component cache. A developer only
needs to clone `lumina`; `make setup` materializes the exact PRomop and wearable
revisions declared in `config/components.yaml`:

```text
lumina/
├── .lumina/components/
│   ├── promop/             # detached, pinned checkout
│   └── lumina-wearables/   # detached, pinned checkout
└── config/components.yaml
```

These checkouts are ignored by Git. Core never uses a mutable branch or a
nearby sibling repository. PRomop is an external dependency; do not copy its
models or create another OMOP or PatientRecord implementation here.

## Quick start

Nix (with flakes enabled), Docker Desktop (or Docker Engine with Compose v2),
and GitHub access to the pinned components are required. The Make targets enter
the Nix development shell automatically when Nix is available. `flake.nix`
declares an immutable nixpkgs revision; Nix writes the matching `flake.lock` on
its first run, which should be committed with the Core release. Docker remains
a host service.

```bash
cd lumina
cp .env.example .env
make setup       # sync exact commits, build in dependency order, then check health
make health
make smoke-test
```

The local endpoints are LUMINA API (`8100`), Archive (`8200`), PRomop
(`8000`), and Wearables (`8300`). `make setup` does not overwrite an existing
`.env`. It starts each service and lets the owning services run their own
migrations.

## Commands

```bash
make start        # start or rebuild the stack
make stop         # stop the stack without removing data volumes
make logs         # follow service logs
make health       # probe every service separately
make smoke-test   # prove source-preserving Archive create/retrieve flow
make versions     # show pinned component revisions
make components   # materialize exact component commits without starting Docker
make check-components  # fail if a cache checkout is missing, dirty, or drifting
make nix-update   # deliberately update locked Nix tooling inputs
```

`config/components.yaml` stores the full immutable commit SHA for every
external component. `scripts/components.py` fetches exactly those object IDs,
checks out detached HEADs, and refuses to replace a dirty checkout. This means
updates are an explicit review-and-test change to the manifest—not an implicit
pull of `main` or `dev`. The resolver also validates each checkout has the
interface that Core builds; it will stop with a remediation message if a pinned
component has not yet published its required service files.

Startup order is fixed: activate the Nix shell (when installed), create/read
`.env`, sync PRomop then Wearables at their pinned commits, build images, start
both databases, migrate and start Archive and PRomop, start Wearables, and only
then start the LUMINA API after all dependency health checks pass.

The current smoke test covers Archive ingestion. Archive-to-OMOP promotion is
intentionally not simulated until an approved transformation and integration
test exist.

## Configuration

Start from `.env.example`; it contains local development values only. Do not
commit `.env` or production credentials. The PRomop service receives the
variables its checked-in Docker configuration actually requires, including its
own database credentials, Django secret key, and admin account.

See `docs/architecture/archive-promop-contract.md` for the data contract and
`config/components.yaml` for tested sibling revisions.
