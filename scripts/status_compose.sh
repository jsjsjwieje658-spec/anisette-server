#!/usr/bin/env bash
# Ghép status.json từ những gì workflow đã có.
#
#   client_info.json  ← GET /v3/client_info của server đang chạy
#   gsa.json          ← kết quả scripts/gsa_probe.py
#   env RUN_ID URL EXPIRES_AT PATCH_MODE DEVICE_ID
#
# Ghi ra $OUT (mặc định /tmp/anisette/status.json) rồi scripts/status_publish.py
# sẽ đẩy lên nhánh `status`.
set -uo pipefail

OUT=${OUT:-/tmp/anisette/status.json}
CI=${CI_FILE:-/tmp/anisette/client_info.json}
GSA=${GSA_FILE:-/tmp/anisette/gsa.json}

CI_JSON=$(cat "$CI" 2>/dev/null || echo '{}')
# md_rinfo chỉ có trong headers v1 (GET /), không có trong /v3/client_info
V1_JSON=$(cat "${V1_PROBE:-/tmp/anisette/v1_probe.json}" 2>/dev/null || echo '{}')
[ -n "$V1_JSON" ] || V1_JSON='{}'
CI_JSON=$(jq -c --argjson v1 "$V1_JSON" '
   . + {md_rinfo: (.md_rinfo // $v1["X-Apple-I-MD-RINFO"] // null),
        device_id: (.device_id // $v1["X-Mme-Device-Id"] // null)}' <<<"$CI_JSON" 2>/dev/null || echo "$CI_JSON")
GSA_JSON=$(cat "$GSA" 2>/dev/null || echo '{}')
[ -n "$CI_JSON" ] || CI_JSON='{}'
[ -n "$GSA_JSON" ] || GSA_JSON='{}'

mkdir -p "$(dirname "$OUT")"
jq -n \
  --argjson ci "$CI_JSON" --argjson gsa "$GSA_JSON" \
  --arg run "${RUN_ID:-}" --arg url "${URL:-}" --arg mode "${PATCH_MODE:-}" \
  --arg dev "${DEVICE_ID:-}" --arg exp "${EXPIRES_AT:-}" \
  --arg now "$(date -u +%FT%TZ)" \
  '{
     updated_at: $now,
     heartbeat_at: $now,
     alive: true,
     run_id: $run,
     url: (if $url == "" then null else $url end),
     anisette_url: (if $url == "" then null else $url end),
     expires_at: (if $exp == "" then null else $exp end),
     identity_mode: (if $mode == "" then null else $mode end),
     client_info: ($ci.client_info // null),
     user_agent: ($ci.user_agent // null),
     device_id: ($ci.device_id // (if $dev == "" then null else $dev end)),
     md_rinfo: ($ci.md_rinfo // null),
     gsa: {
       verdict: ($gsa.verdict // "UNKNOWN"),
       http: ($gsa.http // null),
       ec: ($gsa.ec // null),
       checked_at: $now,
       attempts_used: ($gsa.attempts_used // null)
     },
     protocol: "anisette-v3 (v1 GET / compatible)",
     notes: "alive=false hoặc quá expires_at nghĩa là URL đã chết — đọc lại file này, đừng dùng URL cũ."
   }' > "$OUT"

echo "--- $OUT ---"
cat "$OUT"
