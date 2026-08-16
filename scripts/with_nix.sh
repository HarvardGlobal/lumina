#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${LUMINA_IN_NIX:-}" == "1" || "${LUMINA_USE_NIX:-auto}" == "never" ]]; then
  exec "$@"
fi

if command -v nix >/dev/null 2>&1; then
  cd "$root_dir"
  exec nix develop --accept-flake-config --command env LUMINA_IN_NIX=1 "$@"
fi

echo "[WARN] Nix is not installed; using host tooling. Install Nix to use the pinned flake toolchain." >&2
exec "$@"
