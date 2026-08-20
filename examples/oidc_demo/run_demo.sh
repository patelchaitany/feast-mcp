#!/usr/bin/env bash
#
# One-command setup and demo for the Feast MCP server with OIDC auth.
#
# Starts three processes:
#   1. Mock OIDC server       (port 8081)
#   2. Feast feature server   (port 6566)
#   3. feast-mcp server       (port 8000, reads .env for OIDC config)
#
# Then runs the demo client against the MCP server.
#
# Usage:
#   cd MCP/examples/oidc_demo
#   ./run_demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-$(command -v python3 || command -v python || true)}"
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: python3 or python not found on PATH."
    exit 1
fi

OIDC_PORT=8081
FEAST_PORT=6566
MCP_PORT=8000

OIDC_PID=""
FEAST_PID=""
MCP_PID=""

cleanup() {
    echo ""
    if [[ -n "$MCP_PID" ]]; then
        echo "Stopping feast-mcp server (pid $MCP_PID)..."
        kill "$MCP_PID" 2>/dev/null || true
        wait "$MCP_PID" 2>/dev/null || true
    fi
    if [[ -n "$FEAST_PID" ]]; then
        echo "Stopping Feast feature server (pid $FEAST_PID)..."
        kill "$FEAST_PID" 2>/dev/null || true
        wait "$FEAST_PID" 2>/dev/null || true
    fi
    if [[ -n "$OIDC_PID" ]]; then
        echo "Stopping mock OIDC server (pid $OIDC_PID)..."
        kill "$OIDC_PID" 2>/dev/null || true
        wait "$OIDC_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ── 1. Install dependencies ──────────────────────────────────────────────
echo "==> Step 1/6: Installing dependencies..."
pip install -q "feast" cryptography PyJWT httpx mcp
pip install -q -e "$SCRIPT_DIR/../.."

# ── 2. Start mock OIDC server ────────────────────────────────────────────
echo ""
echo "==> Step 2/6: Starting mock OIDC server on port $OIDC_PORT..."
$PYTHON mock_oidc_server.py "$OIDC_PORT" &
OIDC_PID=$!

echo "    Waiting for OIDC server..."
for i in $(seq 1 10); do
    if curl -sf "http://127.0.0.1:${OIDC_PORT}/.well-known/openid-configuration" > /dev/null 2>&1; then
        echo "    OIDC server is ready."
        break
    fi
    sleep 1
done

if ! curl -sf "http://127.0.0.1:${OIDC_PORT}/.well-known/openid-configuration" > /dev/null 2>&1; then
    echo "ERROR: OIDC server did not start within 10 seconds."
    exit 1
fi

# ── 3. Generate data and apply registry ──────────────────────────────────
echo ""
echo "==> Step 3/6: Generating sample data and applying Feast registry..."
$PYTHON setup_data.py

# ── 4. Start Feast feature server ────────────────────────────────────────
echo ""
echo "==> Step 4/6: Starting Feast feature server on port $FEAST_PORT..."
cd feature_repo
feast serve --host 0.0.0.0 --port "$FEAST_PORT" --no-access-log &
FEAST_PID=$!
cd "$SCRIPT_DIR"

echo "    Waiting for Feast server..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${FEAST_PORT}/health" > /dev/null 2>&1; then
        echo "    Feast server is ready."
        break
    fi
    if ! kill -0 "$FEAST_PID" 2>/dev/null; then
        echo "ERROR: Feast server exited unexpectedly."
        exit 1
    fi
    sleep 1
done

if ! curl -sf "http://localhost:${FEAST_PORT}/health" > /dev/null 2>&1; then
    echo "ERROR: Feast server did not start within 30 seconds."
    exit 1
fi

# ── 5. Start feast-mcp server (reads .env for OIDC config) ──────────────
echo ""
echo "==> Step 5/6: Starting feast-mcp server on port $MCP_PORT..."
echo "    OIDC config loaded from .env"
feast mcp \
    --feast-url "http://localhost:${FEAST_PORT}" \
    --transport sse \
    --port "$MCP_PORT" &
MCP_PID=$!

echo "    Waiting for MCP server..."
sleep 3

if ! kill -0 "$MCP_PID" 2>/dev/null; then
    echo "ERROR: feast-mcp server exited unexpectedly."
    exit 1
fi
echo "    MCP server is ready."

# ── 6. Run the demo client ──────────────────────────────────────────────
echo ""
echo "==> Step 6/6: Running the OIDC demo..."
echo ""
$PYTHON demo_client.py

echo ""
echo "Demo complete."
