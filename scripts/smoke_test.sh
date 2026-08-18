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

if [[ "${LUMINA_ENV:-development}" == "production" ]]; then
  echo "make smoke-test is deliberately disabled in production: it creates synthetic data and production services are private." >&2
  exit 2
fi

archive_port="${ARCHIVE_API_PORT:-8200}"
base_url="http://localhost:${archive_port}/api/v1/archive"
patient_id="synthetic-patient-smoke"
source_system="lumina-smoke"
promop_person_id="990001"
run_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
fhir_source_text="LUMINA Archive smoke ${run_id}"
observed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

curl_archive() {
  if [[ -n "${ARCHIVE_BEARER_TOKEN:-}" ]]; then
    curl -H "Authorization: Bearer ${ARCHIVE_BEARER_TOKEN}" "$@"
  else
    curl "$@"
  fi
}

created="$(curl_archive --fail --silent --show-error -X POST "$base_url/records" \
  -H 'Content-Type: application/json' \
  --data '{"patient_id":"synthetic-patient-smoke","source_system":"lumina-smoke","source_record_id":"smoke-001","record_type":"synthetic-observation","raw_payload":{"value":42,"unit":"arbitrary","source_field":"preserved"},"schema_version":"1.0.0"}')"

record_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$created")"
retrieved="$(curl_archive --fail --silent --show-error "$base_url/records/$record_id")"

python3 -c '
import json, sys
record = json.load(sys.stdin)
assert record["patient_id"] == "synthetic-patient-smoke"
assert record["source_system"] == "lumina-smoke"
assert record["raw_payload"]["source_field"] == "preserved"
assert record["raw_payload"]["value"] == 42
' <<<"$retrieved"

echo "[OK] Archive synthetic smoke test (record $record_id)"

# The promoted FHIR test uses a dedicated, local-only PRomop Person. PRomop
# owns its OMOP write; Archive only sends preserved source bytes and records
# the returned target IDs as lineage.
"$root_dir/scripts/compose.sh" exec -T promop python manage.py shell -c \
  "from omop_core.models import Person; Person.objects.get_or_create(person_id=${promop_person_id})" >/dev/null

fhir_bundle="$(python3 - "$run_id" "$fhir_source_text" "$observed_at" <<'PY'
import json
import sys

run_id, source_text, observed_at = sys.argv[1:]
print(json.dumps({
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [{"resource": {
        "resourceType": "Observation",
        "id": f"archive-smoke-{run_id}",
        "status": "final",
        "code": {"text": source_text, "coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
        "effectiveDateTime": observed_at,
        "valueQuantity": {"value": 72, "unit": "beats/min"},
    }}],
}))
PY
)"

fhir_created="$(curl_archive --fail --silent --show-error -X POST \
  "$base_url/fhir?source_system=lumina-smoke-fhir-${run_id}" \
  -H 'Content-Type: application/fhir+json' \
  -H 'FHIR-Version: R4' \
  --data "$fhir_bundle")"
fhir_record_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["record_id"])' <<<"$fhir_created")"

promotion="$(curl_archive --fail --silent --show-error -X POST \
  "$base_url/records/$fhir_record_id/promote/promop" \
  -H 'Content-Type: application/json' \
  --data "{\"promop_person_id\":${promop_person_id}}")"
promotion_id="$(python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result["status"] == "succeeded"
assert result["target_details"]["person_id"] == 990001
print(result["id"])
' <<<"$promotion")"

measurement_count="$("$root_dir/scripts/compose.sh" exec -T promop env \
  LUMINA_SMOKE_PERSON_ID="$promop_person_id" LUMINA_SMOKE_SOURCE="$fhir_source_text" \
  python manage.py shell -c "import os; from omop_core.models import Measurement; print(Measurement.objects.filter(person_id=int(os.environ['LUMINA_SMOKE_PERSON_ID']), measurement_source_value=os.environ['LUMINA_SMOKE_SOURCE']).count())" \
  | tail -n 1)"
[[ "$measurement_count" == "1" ]]

retry_status="$(curl_archive --silent --show-error -o /tmp/lumina-smoke-promotion.json -w '%{http_code}' -X POST \
  "$base_url/records/$fhir_record_id/promote/promop" \
  -H 'Content-Type: application/json' \
  --data "{\"promop_person_id\":${promop_person_id}}")"
[[ "$retry_status" == "200" ]]
retry_promotion_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' </tmp/lumina-smoke-promotion.json)"
[[ "$retry_promotion_id" == "$promotion_id" ]]

lineage="$(curl_archive --fail --silent --show-error "$base_url/records/$fhir_record_id/lineage")"
python3 -c '
import json, sys
lineage = json.load(sys.stdin)
assert lineage["promotions"][0]["status"] == "succeeded"
assert any(event["event_type"] == "promoted" for event in lineage["events"])
' <<<"$lineage"

echo "[OK] Archive -> PRomop -> OMOP smoke test (Archive $fhir_record_id, promotion $promotion_id)"
