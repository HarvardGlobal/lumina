#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

source "$root_dir/scripts/ensure_env.sh"
python3 "$root_dir/scripts/validate_production_config.py"
python3 "$root_dir/scripts/components.py" sync
command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required." >&2; exit 1; }

"$root_dir/scripts/compose.sh" up -d --build
