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

archive_port="${ARCHIVE_API_PORT:-8200}"
base_url="http://localhost:${archive_port}/api/v1/archive"
patient_id="synthetic-patient-smoke"
source_system="lumina-smoke"

created="$(curl --fail --silent --show-error -X POST "$base_url/records" \
  -H 'Content-Type: application/json' \
  --data '{"patient_id":"synthetic-patient-smoke","source_system":"lumina-smoke","source_record_id":"smoke-001","record_type":"synthetic-observation","raw_payload":{"value":42,"unit":"arbitrary","source_field":"preserved"},"schema_version":"0.1.0"}')"

record_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$created")"
retrieved="$(curl --fail --silent --show-error "$base_url/records/$record_id")"

python3 -c '
import json, sys
record = json.load(sys.stdin)
assert record["patient_id"] == "synthetic-patient-smoke"
assert record["source_system"] == "lumina-smoke"
assert record["raw_payload"]["source_field"] == "preserved"
assert record["raw_payload"]["value"] == 42
' <<<"$retrieved"

echo "[OK] Archive synthetic smoke test (record $record_id)"
echo "SKIPPED: OMOP/PatientRecord promotion not yet implemented"
