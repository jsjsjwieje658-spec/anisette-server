#!/usr/bin/env bash
# Khởi động / xoay danh tính / dừng server anisette-v3.
#
#   start_server.sh start            # khởi động, chờ tới khi GET / có X-Apple-I-MD-M
#   start_server.sh rotate           # xoá device.json + provisioning rồi khởi động lại
#   start_server.sh stop             # dừng
#
# Biến môi trường:
#   BIN     đường dẫn binary anisette-v3-server
#   ADI     thư mục --adi-path (device.json + provisioning nằm ở đây)
#   PORT    cổng (mặc định 6969)
#   RUNLOG  file log của server (mặc định /tmp/anisette/server.log)
#   PIDFILE file pid (mặc định /tmp/anisette/pid)
#
# Vì sao có "rotate": machine-id do ADI sinh ra có thể bị Apple ghì (503/-36607)
# hoặc đã bị từ chối. device.json là thứ duy nhất giữ danh tính, xoá nó là lần
# khởi động sau ADI sẽ provision một machine-id mới (xem README §"đo đạc").
set -uo pipefail

BIN=${BIN:?cần BIN}
ADI=${ADI:?cần ADI}
PORT=${PORT:-6969}
RUNLOG=${RUNLOG:-/tmp/anisette/server.log}
PIDFILE=${PIDFILE:-/tmp/anisette/pid}

mkdir -p "$(dirname "$RUNLOG")" "$(dirname "$PIDFILE")" "$ADI"

stop_server() {
  if [ -f "$PIDFILE" ]; then
    local pid; pid=$(cat "$PIDFILE")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
}

start_server() {
  nohup "$BIN" --host 0.0.0.0 --port "$PORT" \
      --adi-path "$ADI" --timeout 15000 >> "$RUNLOG" 2>&1 &
  echo $! > "$PIDFILE"
  echo "[start] pid=$(cat "$PIDFILE") adi=$ADI port=$PORT"

  # pha 1: HTTP server sống (tối đa ~120s)
  local up=0
  for i in $(seq 1 60); do
    if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/v3/client_info" >/dev/null 2>&1; then
      up=1; echo "[start] /v3/client_info OK sau ${i}x2s"; break
    fi
    sleep 2
    if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "[start] server chết khi khởi động" >&2
      tail -60 "$RUNLOG" >&2
      return 1
    fi
  done
  [ "$up" = 1 ] || { echo "[start] server không mở cổng $PORT" >&2; tail -60 "$RUNLOG" >&2; return 1; }

  # pha 2: ADI đã provision (GET / phải có X-Apple-I-MD-M), tối đa 3 lần
  local k
  for k in 1 2 3; do
    if curl -fsS --max-time 60 "http://127.0.0.1:${PORT}/" -o /tmp/anisette/v1_probe.json 2>/dev/null \
       && grep -q 'X-Apple-I-MD-M' /tmp/anisette/v1_probe.json; then
      echo "[start] GET / có X-Apple-I-MD-M (ADI đã provision, lần $k)"
      jq -r 'to_entries[] | "  \(.key): \(.value)"' /tmp/anisette/v1_probe.json 2>/dev/null || true
      return 0
    fi
    echo "[start] GET / chưa có X-Apple-I-MD-M (lần $k) — thử lại"
    sleep 5
  done
  echo "[start] GET / không trả X-Apple-I-MD-M" >&2
  tail -40 "$RUNLOG" >&2 || true
  return 1
}

case "${1:-start}" in
  start)
    stop_server
    start_server
    ;;
  rotate)
    stop_server
    echo "[rotate] xoá danh tính cũ: $ADI/device.json + $ADI/provisioning"
    rm -f "$ADI/device.json"
    rm -rf "$ADI/provisioning"
    start_server
    ;;
  stop)
    stop_server
    echo "[stop] đã dừng"
    ;;
  *)
    echo "usage: $0 {start|rotate|stop}" >&2
    exit 2
    ;;
esac
