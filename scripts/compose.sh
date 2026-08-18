#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

if [[ "${LUMINA_ENV:-development}" == "production" ]]; then
  exec docker compose -f compose.yaml -f compose.production.yaml "$@"
fi

exec docker compose "$@"
