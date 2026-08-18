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
needs to clone `lumina`; `make setup` materializes the exact PRomop, LUMINA
Wearables, and Open Wearables revisions declared in `config/components.yaml`:

```text
lumina/
├── .lumina/components/
│   ├── promop/             # detached, pinned checkout
│   ├── lumina-wearables/   # detached, pinned checkout
│   └── open-wearables/     # detached, pinned upstream checkout
└── config/components.yaml
```

These checkouts are ignored by Git. Core never uses a mutable branch or a
nearby sibling repository. PRomop is an external dependency; do not copy its
models or create another OMOP or PatientRecord implementation here.

Open Wearables is pinned at upstream release `0.7.0` and commit
`cb3ad1fd1141138179d27f7e787a1d0049a071c9`. Component resolution verifies
both the immutable Git object and the upstream `backend/pyproject.toml` version
before it reports the checkout healthy. Wearables is likewise pinned by SHA and
its `VERSION` file. The commit SHA is the authoritative reproducibility lock;
the release number is a human-readable compatibility check.

## Start the complete stack from Core

You only clone this repository. Do **not** clone PRomop, Wearables, or Open
Wearables next to it: Core fetches the tested revisions itself into
`.lumina/components`.

Before starting, ensure that:

- Docker Desktop is running (or Docker Engine and Compose v2 are available).
- Your SSH key can read `healthkey-ai/promop` and
  `HarvardGlobal/lumina-wearables`; Core uses their SSH clone URLs when it
  materializes the pinned revisions. Open Wearables is public and fetched over
  HTTPS.
- Nix with flakes enabled is installed for the reproducible toolchain. The
  Make targets enter the committed Nix flake automatically. The flake provides
  pinned Python 3.12 plus every Core runtime import (FastAPI, SQLAlchemy,
  PyArrow, boto3, and related packages), pytest/coverage, pip-audit, Bandit,
  Git, Make, curl, and jq. Docker Desktop/Engine remains a host prerequisite.
  If Nix is absent, orchestration can use host Git/Python with a warning, but
  `make test` requires a project `.venv`; that is not the reproducible setup.

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
3. Fetches PRomop, Wearables, and Open Wearables at the full commit SHAs in
   `config/components.yaml`, checks them out at detached HEADs, and verifies
   their required service files.
4. Builds the Core, Archive, PRomop, and Wearables images.
5. Starts both PostgreSQL databases, then migrates and starts Archive and
   PRomop, starts Wearables, and finally starts the LUMINA API after its
   dependencies are healthy.
6. Probes every service and fails the command if a health check does not pass.

Open Wearables is version-pinned and fetched in step 3 but is not started by
the default Compose stack. It is an upstream application with its own OAuth,
administrator, PostgreSQL, Redis, and worker lifecycle. Configure and deploy
that application separately, then set `OPEN_WEARABLES_BASE_URL` (including
`/api/v1`) and inject `OPEN_WEARABLES_API_KEY`. This prevents `make setup` from
silently creating an unconfigured patient-identity system.

The Nix flake also provides an explicit Open Wearables tooling shell. It uses
the pinned Nix package set and supplies the upstream-required Python 3.13,
`uv`, Node.js, and pnpm; the upstream `uv.lock` and `pnpm-lock.yaml` then lock
its project dependencies. It does not mutate the detached component checkout:

```bash
make open-wearables-shell
# Inside the shell, inspect the pinned source:
cd .lumina/components/open-wearables
uv --version
```

Docker Desktop/Engine and a separately configured Open Wearables deployment
remain host/deployment prerequisites. Do not create its `backend/config/.env`
inside `.lumina/components`: that would make the immutable source cache dirty.
Keep configuration and secrets in the deployment environment instead.

### Edit Open Wearables safely

Use the immutable component cache to run LUMINA; use a separate editable
workspace checkout to investigate or contribute an upstream fix:

```bash
make open-wearables-workspace
make open-wearables-shell
```

The first command creates `../open-wearables` at the exact manifest revision
on branch `lumina/open-wearables-0.7.0`; the supplied VS Code workspace includes
it as **Open Wearables (editable upstream)**. A change there does not alter a
running LUMINA stack. Commit it to an appropriate fork/upstream branch, then
review, test, and replace the `open-wearables.git_ref` in
`config/components.yaml` with the new full SHA. `make components` then updates
the clean runtime cache reproducibly.

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

`make smoke-test` proves the Archive create/retrieve flow. The supported
Archive-to-OMOP path is an explicit FHIR Bundle promotion, described below.

## Wearable pilot

Wearables `1.1.1` adds a deliberately narrow Open Wearables read-only pilot:
provider-supplied daily resting heart rate and HRV-SDNN. Its API returns a
transparent daily preview with provider, device, source-metric, and temporal
resolution provenance. It does not perform calculations, imputation, or a
database write. The human lookup sheet and the exact source-field mappings are
in the pinned Wearables repository at `docs/metric-cheat-sheet.md`.

This release does not yet write those samples into PRomop. The current PRomop
wearable endpoint accepts native Garmin FIT and Apple Health ZIP files; it does
not provide an authenticated endpoint for canonical daily service-to-service
records. LUMINA therefore does not bypass PRomop or fabricate a provider file.
The proposed PRomop-owned import contract is documented in Wearables at
`docs/promop-integration.md`; it is the next prerequisite for a direct
PRomop-only integration.

For a full LUMINA deployment, raw Open Wearables responses can later be stored
in Archive before a selected, approved daily metric is promoted to PRomop. Raw
continuous heart rate and HRV-RMSSD are explicitly excluded from this pilot:
they require independent aggregation, vocabulary, and governance decisions.
The required raw-object, device, subject-identity, mapping-version, correction,
and promotion lineage is defined in
[docs/architecture/wearable-data-lineage.md](docs/architecture/wearable-data-lineage.md).

## Archive to PRomop / OMOP

Archive is always the first destination: it preserves the complete received
payload and records provenance before any standardization. PRomop owns all
FHIR-to-OMOP interpretation and writes the resulting OMOP rows; Archive never
writes the PRomop database directly.

The currently supported promotion path is a stored FHIR R4 Bundle. It requires
an existing PRomop `Person` and an explicit numeric `promop_person_id`; Archive
does not guess or resolve clinical identity. The shared
`PROMOP_SERVICE_AUTH_TOKEN` authenticates Archive to PRomop. The example value
in `.env.example` is strictly for local development and must be replaced for a
deployed environment.

```bash
# 1. Preserve the original FHIR Bundle in Archive.
curl -X POST 'http://localhost:8200/api/v1/archive/fhir?source_system=my-ehr' \
  -H 'Content-Type: application/fhir+json' \
  -H 'FHIR-Version: R4' \
  --data-binary @bundle.json

# 2. Use the returned record_id and explicitly choose its PRomop Person.
curl -X POST "http://localhost:8200/api/v1/archive/records/<record_id>/promote/promop" \
  -H 'Content-Type: application/json' \
  --data '{"promop_person_id": 12345}'

# 3. Inspect receipt, preserved source, PRomop result, and provenance.
curl "http://localhost:8200/api/v1/archive/records/<record_id>/lineage"
```

The promotion response and lineage include the PRomop result (for example,
the OMOP `measurement_ids`) and the mapping/transform versions. Repeating the
same successful record/person/version request returns the existing lineage
record and does not submit the Bundle a second time. A PRomop failure is
recorded as failed provenance while the preserved Archive source remains
available for a corrected retry.

Only object-backed FHIR Bundles are eligible today. Generic JSON, raw binary,
and wearable Parquet data remain Archive-only until a separately approved,
versioned aggregation and PRomop mapping is implemented and tested. In
particular, do not promote high-frequency wearable samples directly as OMOP
measurements.

## Commands

```bash
make start        # start or rebuild the stack
make stop         # stop the stack without removing data volumes
make logs         # follow service logs
make health       # probe every service separately
make smoke-test   # prove Archive preservation, FHIR promotion, and OMOP lineage
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

### Nix toolchain details

The committed `flake.lock` fixes the Nix package set; `flake.nix` then selects
Python 3.12 and the complete Core import/test/security toolchain from that
fixed package set. Enter it explicitly with:

```bash
nix develop
python3 --version
python3 -c 'import fastapi, sqlalchemy, pyarrow, boto3; print("Core imports OK")'
make test
```

`make setup`, `make start`, `make build`, `make components`, and
`make check-components` enter the same shell automatically. Docker images
still install the exact version pins in `services/archive/requirements.txt`
and `services/api/requirements.txt`; review both the Nix lock and those runtime
requirements when updating Python dependencies. Use `nix flake check` and
`nix fmt` before changing the flake.

## Configuration

Start from `.env.example`; it contains local development values only. Do not
commit `.env` or production credentials. The PRomop service receives the
variables its checked-in Docker configuration actually requires, including its
own database credentials, Django secret key, and admin account.

See `docs/architecture/archive-promop-contract.md` for the data contract and
`docs/architecture/archive-storage.md` for the Archive's object, Parquet,
identity, lineage, and local-security design. See `config/components.yaml` for
tested sibling revisions.

## Patient-data deployment and compliance boundary

**Do not put patient data into the default local stack.** `.env.example`, the
default Compose file, localhost ports, Docker volumes, and `make smoke-test`
are for development and synthetic data only. The smoke test deliberately
creates a synthetic PRomop person and observation and is blocked when
`LUMINA_ENV=production`.

The production profile is a technical baseline, not a legal certification.
Whether HIPAA, GDPR, UK GDPR, research ethics, data-residency, or another
regime applies depends on the organisation, purpose, geography, contracts, and
data flows. HIPAA's Security Rule requires administrative, physical, and
technical safeguards, including access control, audit controls, integrity,
authentication, and transmission security; source code alone cannot supply all
of those controls. Review the [HHS Security Rule summary](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html)
with your privacy, security, legal, and clinical-governance owners before any
live use.

### What the production profile enforces

Set `LUMINA_ENV=production` and run `make start`. Core will use
`compose.production.yaml` and refuse to start unless all of the following are
true:

- Archive has a unique bearer secret of at least 32 characters; **every**
  `/api/v1/archive/*` route, including catalogue, patient, metadata, and
  lineage routes, requires it. Responses are marked `Cache-Control: no-store`.
- Archive body size and a per-process rate-limit backstop are enabled. Your
  ingress must add a shared, identity/IP-aware rate limit as the app backstop
  is not a replacement for a distributed gateway control.
- Archive uses an S3-compatible private bucket with `aws:kms` server-side
  encryption and a named KMS key. The local filesystem object store is rejected
  in production.
- PRomop debug mode is off, public URLs are HTTPS, and known local/default
  passwords, Django secret, service token, and database credentials are
  rejected.
- Compose publishes no service ports. Archive, PRomop, Wearables, databases,
  and the Core API remain on the private service network; documentation/OpenAPI
  endpoints are disabled for Archive in production.

Copy the names and non-secret structure from `.env.production.example` into
your secret manager/deployment environment. Do not copy it verbatim into Git,
place cloud access keys in it, or use long-lived static cloud credentials.
Archive obtains S3 credentials through the normal workload-identity chain.

```bash
# After injecting real values through your secret manager/deployment platform:
export LUMINA_ENV=production
make start       # validates configuration before any container is started
make health      # probes services from the private Compose network
```

`make health` is a liveness check, not an external security acceptance test.
Production traffic must enter through a separately managed TLS gateway/load
balancer with a valid certificate, modern TLS policy, OIDC/MFA-backed user
authentication, role/tenant authorization, request logging/redaction, WAF and
rate limits. Do not expose the Archive bearer token to browsers or end users;
it is only a machine-to-machine credential. Deploy a gateway policy that only
allows the approved service identities to call Archive and PRomop, and applies
least privilege to each database, bucket prefix, and KMS key.

### Required release gate before live data

An authorised release owner must record evidence for each item below. A failed
or unowned item means the environment is **not ready for patient data**.

| Gate | Required evidence |
| --- | --- |
| Scope and lawful use | Jurisdiction/data classification, approved purpose, data-flow diagram, named data owner, privacy/legal review, consent/IRB basis where applicable. |
| Identity and access | OIDC/MFA gateway configuration, least-privilege role matrix, break-glass procedure, service-account inventory, quarterly access-review owner. |
| Encryption and secrets | TLS test, private bucket policy, KMS key policy/rotation, workload identity, secret-manager references, and proof no credentials are committed or logged. |
| Infrastructure | Private network/firewall rules, hardened hosts, supported OS/container base images, vulnerability remediation SLA, and platform audit logs. |
| Resilience | Encrypted database and object backups, restoration test with recorded RPO/RTO, disaster-recovery owner, retention/deletion and legal-hold policy. |
| Detection and response | Central immutable audit-log retention, alerting/on-call, incident and breach-response runbook, tabletop exercise, and vulnerability disclosure process. |
| Clinical data safety | Source validation rules, identity-linkage ownership, mapping/version approval, clinical review of each promotion type, and rollback/correction procedure. |
| Verification | Passing pinned-component checks, tests, dependency scan, image scan, penetration test appropriate to exposure, and signed release/change record. |
| Third parties | Signed required agreements (for example BAAs/DPA), approved cloud region/subprocessors, and vendor risk assessment. |

Archive preserves source bytes and records promotion lineage, but it does not
decide patient consent, identity matching, clinical appropriateness, retention,
or legal disclosure. PRomop promotion remains limited to an explicitly selected
person and preserved FHIR Bundle; wearable and generic source data stay
Archive-only until a reviewed, versioned clinical transformation is approved.

### Technical operations appendix

1. **Network and ingress:** provision a private container/network environment
   and attach only the authenticated TLS gateway. Keep databases and object
   storage private. Do not re-add host ports from `compose.yaml` to the
   production overlay.
2. **Object store:** create a dedicated private S3 bucket/prefix, block public
   access, require KMS encryption and TLS, enable object versioning and the
   retention/object-lock policy approved by governance. Grant Archive only the
   needed prefix and KMS actions through workload identity.
3. **Database:** use a managed/private PostgreSQL service or an equivalently
   operated service with encryption, backups, patching, access audit, and a
   tested restoration procedure. Do not rely on the Compose named volumes for
   production persistence.
4. **Observability:** send container, gateway, database, cloud audit, and
   Archive provenance events to a protected central logging system. Redact PHI,
   authorization headers, tokens, request bodies, and query values before logs
   leave the workload. Define who reviews access and alert records.
5. **Change management:** update Nix locks and component SHA pins only through
   reviewed releases. Run `make check-components`, the test suite, dependency
   and image scans, and the relevant PRomop tests before promotion. Review
   `SECURITY.md` and replace the fallback `CODEOWNERS` entries with named
   accountable owners.

The Core CI runs Archive/API tests with an 80% line-coverage floor, audits the
pinned Python dependencies, and performs static security analysis. Coverage is
a regression signal, not proof of clinical correctness or security;
integration, migration, backup/restore, gateway, and adversarial tests remain
release-gate requirements.
