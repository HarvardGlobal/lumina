#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example (review local-only values before shared use)."
fi

set -a
# shellcheck disable=SC1091
source .env
set +a
