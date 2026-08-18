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
compose_cmd=("$root_dir/scripts/compose.sh")

check_http() {
  local label="$1" url="$2"
  if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
    echo "[OK] $label"
  else
    echo "[FAIL] $label" >&2
    failed=1
  fi
}

if [[ "${LUMINA_ENV:-development}" == "production" ]]; then
  check_container_http() {
    local service="$1" label="$2" url="$3"
    if "${compose_cmd[@]}" exec -T "$service" python -c "import urllib.request; urllib.request.urlopen('${url}', timeout=5)" >/dev/null 2>&1; then
      echo "[OK] $label (private service network)"
    else
      echo "[FAIL] $label" >&2
      failed=1
    fi
  }
  check_container_http lumina-api "LUMINA API" "http://localhost:8100/health"
  check_container_http archive "Archive API" "http://localhost:8200/health"
  check_container_http promop "PRomop API" "http://localhost:8000/api/health/"
  check_container_http wearables "Wearables service" "http://localhost:8300/health"
else
  check_http "LUMINA API" "http://localhost:${api_port}/health"
  check_http "Archive API" "http://localhost:${archive_port}/health"
  check_http "PRomop API" "http://localhost:${promop_port}/api/health/"
  check_http "Wearables service" "http://localhost:${wearables_port}/health"
fi
if "${compose_cmd[@]}" exec -T archive-db pg_isready -U "$archive_db_user" -d "$archive_db_name" >/dev/null 2>&1; then
  echo "[OK] Archive PostgreSQL"
else
  echo "[FAIL] Archive PostgreSQL" >&2
  failed=1
fi
exit "$failed"
