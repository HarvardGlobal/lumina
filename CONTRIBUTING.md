# Contributing to LUMINA

Thank you for contributing. LUMINA processes health-data infrastructure; do
not put patient data, credentials, production URLs, or sensitive screenshots in
issues, pull requests, tests, or commits.

## Before opening a pull request

1. Search existing issues and pull requests, then discuss material design or
   clinical-semantics changes before implementing them.
2. Create a focused branch and keep unrelated formatting changes out of it.
3. Preserve the Core component model: publish a component change in its own
   repository, then update its full immutable SHA in `config/components.yaml`.
   Do not edit `.lumina/components` as if it were source.
4. Run `make test`, `make check-components`, and the relevant Docker build.
   Document any check you could not run and why.

## Data and mapping changes

Changes that ingest, transform, archive, or promote health data must state the
source format, identity boundary, schema/mapping version, provenance, expected
units, validation, correction/replay behaviour, and test data provenance.
Never infer patient identity from a device or provider identifier. Do not claim
clinical validation or regulatory compliance without the applicable review.

## Pull requests

Use a clear summary, link the relevant issue/design discussion, describe test
coverage, and identify compatibility or security impacts. By submitting a
contribution, you confirm that you have the right to submit it under the
repository's Apache-2.0 licence.

## Reporting vulnerabilities

Follow [SECURITY.md](SECURITY.md); do not disclose vulnerabilities publicly.
