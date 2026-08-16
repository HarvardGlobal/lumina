#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

source "$root_dir/scripts/ensure_env.sh"
python3 "$root_dir/scripts/components.py" sync
docker compose build
