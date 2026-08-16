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

## Start the complete stack from Core

You only clone this repository. Do **not** clone PRomop or Wearables next to
it: Core fetches the tested revisions itself into `.lumina/components`.

Before starting, ensure that:

- Docker Desktop is running (or Docker Engine and Compose v2 are available).
- Your SSH key can read `healthkey-ai/promop` and
  `HarvardGlobal/lumina-wearables`; Core uses their SSH clone URLs when it
  materializes the pinned revisions.
- Nix with flakes enabled is installed for the reproducible toolchain. The
  Make targets enter the committed Nix flake automatically. If Nix is absent,
  they continue using host Git and Python with a warning, but that is not the
  reproducible setup.

```bash
git clone git@github.com:HarvardGlobal/lumina.git
cd lumina
make setup
```

`make setup` is the complete first-start command. It performs these steps in
this order:

1. Enters the Nix development shell when Nix is installed.
2. Creates `.env` from `.env.example` if needed, without overwriting an
   existing `.env`.
3. Fetches PRomop and Wearables at the full commit SHAs in
   `config/components.yaml`, checks them out at detached HEADs, and verifies
   their required service files.
4. Builds the Core, Archive, PRomop, and Wearables images.
5. Starts both PostgreSQL databases, then migrates and starts Archive and
   PRomop, starts Wearables, and finally starts the LUMINA API after its
   dependencies are healthy.
6. Probes every service and fails the command if a health check does not pass.

The first run can take several minutes because Docker downloads base images and
PRomop installs Python and frontend dependencies. Later starts reuse Docker and
Nix caches.

When setup finishes, open or probe these local services:

| Service | Address | Health endpoint |
| --- | --- | --- |
| LUMINA API | `http://localhost:8100` | `http://localhost:8100/health` |
| Archive | `http://localhost:8200` | `http://localhost:8200/health` |
| PRomop | `http://localhost:8000` | `http://localhost:8000/api/health/` |
| Wearables | `http://localhost:8300` | `http://localhost:8300/health` |

Then verify the running stack:

```bash
make health
make smoke-test
```

`make smoke-test` proves the Archive create/retrieve flow. Archive-to-OMOP
promotion is intentionally not simulated until an approved transformation and
integration test exist.

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

Use `make start` after the first setup to start or rebuild the stack. Use
`make stop` to stop it while preserving the PostgreSQL volumes. Use
`make components` when you only need to fetch the pinned source checkouts, and
`make check-components` before a build or release to confirm they are present,
clean, and at the declared revisions.

`config/components.yaml` stores the full immutable commit SHA for every
external component. `scripts/components.py` fetches exactly those object IDs,
checks out detached HEADs, and refuses to replace a dirty checkout. This means
updates are an explicit review-and-test change to the manifest—not an implicit
pull of `main` or `dev`. The resolver also validates each checkout has the
interface that Core builds; it will stop with a remediation message if a pinned
component has not yet published its required service files.

## Version management

`flake.nix` and the committed `flake.lock` pin the Nix toolchain. The component
manifest pins each external repository by a full 40-character commit SHA. To
upgrade a component, publish and test the compatible component revision, change
its SHA in `config/components.yaml`, run `make components`, `make health`, and
the relevant tests, then commit the manifest change. Never change the manifest
to a branch name such as `main` or `dev`.

`make nix-update` deliberately updates the Nix lock file. Review and test that
change, then commit `flake.lock` with the Core release.

## Configuration

Start from `.env.example`; it contains local development values only. Do not
commit `.env` or production credentials. The PRomop service receives the
variables its checked-in Docker configuration actually requires, including its
own database credentials, Django secret key, and admin account.

See `docs/architecture/archive-promop-contract.md` for the data contract and
`config/components.yaml` for tested sibling revisions.
