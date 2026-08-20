#!/usr/bin/env bash
#
# Runs the OTEL demo end to end:
#   1. starts a local OpenTelemetry Collector + OpenObserve UI (Docker),
#   2. sets up sample data and applies the Feast registry,
#   3. starts a real Feast feature server,
#   4. starts feast-mcp with OTLP export enabled,
#   5. tails the collector so you can watch the exported log records.
#
# View the logs in the UI at http://localhost:5080 (root@example.com / Complexpass@123).
# Stop everything with Ctrl-C.

set -euo pipefail
cd "$(dirname "$0")"

FEAST_PORT="${FEAST_PORT:-6566}"
FEAST_URL="http://localhost:${FEAST_PORT}"
OTEL_ENDPOINT="${OTEL_ENDPOINT:-http://localhost:4317}"

cleanup() {
  echo
  echo "Stopping..."
  [[ -n "${MCP_PID:-}" ]] && kill "$MCP_PID" 2>/dev/null || true
  [[ -n "${FEAST_PID:-}" ]] && kill "$FEAST_PID" 2>/dev/null || true
  docker compose down 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting OpenTelemetry Collector + OpenObserve UI (Docker)"
docker compose up -d
echo "    OpenObserve UI: http://localhost:5080  (root@example.com / Complexpass@123)"
sleep 5

echo "==> Setting up sample data + Feast registry"
python setup_data.py

echo "==> Starting Feast feature server on port ${FEAST_PORT}"
(cd feature_repo && feast serve --host 0.0.0.0 --port "${FEAST_PORT}") &
FEAST_PID=$!
sleep 5

echo "==> Starting feast-mcp with OTLP export -> $OTEL_ENDPOINT"
feast mcp \
  --feast-url "$FEAST_URL" \
  --transport http --port 8000 \
  --log-level INFO \
  --log-format json \
  --otel-endpoint "$OTEL_ENDPOINT" &
MCP_PID=$!
sleep 4

echo "==> Firing a round of test calls (demo_client.py) to generate logs"
python demo_client.py || echo "    (client pass failed — you can retry: python demo_client.py)"

echo
echo "==> Up. Browse logs in the UI: http://localhost:5080 -> Logs -> 'default'"
echo "    Generate more traffic anytime:  python demo_client.py --loop"
echo "==> Watching collector output (Ctrl-C to stop)."
echo "    Every feast-mcp log line should also appear below as a LogRecord."
echo
docker compose logs -f otel-collector
