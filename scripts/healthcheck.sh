#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

api_port="${LUMINA_API_PORT:-8100}"
archive_port="${ARCHIVE_API_PORT:-8200}"
promop_port="${PROMOP_API_PORT:-8000}"
wearables_port="${WEARABLES_API_PORT:-8300}"
archive_db_user="${ARCHIVE_DB_USER:-lumina}"
archive_db_name="${ARCHIVE_DB_NAME:-lumina_archive}"
failed=0

check_http() {
  local label="$1" url="$2"
  if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
    echo "[OK] $label"
  else
    echo "[FAIL] $label" >&2
    failed=1
  fi
}

check_http "LUMINA API" "http://localhost:${api_port}/health"
check_http "Archive API" "http://localhost:${archive_port}/health"
if docker compose exec -T archive-db pg_isready -U "$archive_db_user" -d "$archive_db_name" >/dev/null 2>&1; then
  echo "[OK] Archive PostgreSQL"
else
  echo "[FAIL] Archive PostgreSQL" >&2
  failed=1
fi
check_http "PRomop API" "http://localhost:${promop_port}/api/health/"
check_http "Wearables service" "http://localhost:${wearables_port}/health"

exit "$failed"
