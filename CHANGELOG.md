# Changelog

## Unreleased

- Added a Nix flake for a pinned developer toolchain.
- Made Core self-contained: external components are fetched into a
  core-managed cache at immutable manifest revisions before every build/start.

## 0.1.0

- Initial local orchestration stack.
- Source-preserving Archive API and PostgreSQL schema.
- LUMINA dependency status API, component version manifest, health checks, and
  synthetic Archive smoke test.
