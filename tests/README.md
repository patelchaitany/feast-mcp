# MCP SDK Migration Test Suite

Test suite for validating the migration from Feast's `fastapi_mcp` auto-wrapper to a purpose-built MCP SDK server. Covers every endpoint on both the feature server (11 endpoints) and registry server (67 endpoints).

## Architecture

The standalone MCP server (`feast-mcp`) is a **separate process** that proxies tool calls to the upstream Feast servers over HTTP. It is NOT mounted on the feature server — it runs on its own port.

```
test
  |-- REST call ---------> feature_server (port A)     feast serve
  |-- REST call ---------> registry_server (port B)    feast serve_registry
  |-- MCP SDK call ------> mcp_server (port C)         feast-mcp --feast-url ...
                                |
                                +-- HTTP proxy --> feature_server (port A)
```

Auth is pass-through: the MCP server forwards the caller's bearer token to the upstream Feast server, which performs OIDC/Kubernetes token validation and RBAC enforcement.

## What This Does

1. **REST Baseline** -- calls every Feast endpoint directly via HTTP and verifies valid responses
2. **MCP Comparison** -- for migrated tools, calls the same operation via the standalone MCP server and asserts the output matches the REST response exactly
3. **Coverage Check** -- auto-discovers endpoints from OpenAPI and warns if any are missing from the manifest
4. **Authorization** -- validates 401/403 error codes with mock OIDC (no token, invalid token, wrong role)
5. **Migration Report** -- prints a checklist after every run showing which tools are migrated and passing

## Quick Start

```bash
# Install dependencies (from MCP/ directory)
make install

# Run all tests (starts servers automatically)
make test

# Run just the feature server tests
make test-feature-server

# Run just the registry tests
make test-registry

# Run just the coverage check
make test-discovery

# Run just the auth tests
make test-auth

# Run everything except auth
make test-no-auth
```

## External Server Mode

By default, the test suite starts and stops all servers automatically. But
when you're developing or debugging, you probably want to start servers
yourself in separate terminals and point the tests at them.

Set environment variables to skip automatic server startup:

| Env var | What it overrides | Example |
|---|---|---|
| `FEAST_FEATURE_SERVER_URL` | Feature server | `http://localhost:6566` |
| `FEAST_REGISTRY_SERVER_URL` | Registry server (include `/api/v1`) | `http://localhost:6572/api/v1` |
| `FEAST_MCP_SERVER_URL` | Standalone MCP server | `http://localhost:8000` |
| `FEAST_MOCK_OIDC_URL` | Mock OIDC server (auth tests) | `http://localhost:8081` |
| `FEAST_AUTH_FEATURE_SERVER_URL` | Feature server with auth (auth tests) | `http://localhost:6567` |
| `FEAST_AUTH_REGISTRY_SERVER_URL` | Registry server with auth (auth tests) | `http://localhost:6573/api/v1` |

Each variable is independent -- set one to use your own server for that
component, leave it unset to let the test suite manage it.

When all three main URLs are set (`FEAST_FEATURE_SERVER_URL`,
`FEAST_REGISTRY_SERVER_URL`, `FEAST_MCP_SERVER_URL`), the feature repo
setup (apply + materialize) is skipped entirely since your servers
already have data.

### Example: debug the MCP server

Start servers in three terminals:

```bash
# Terminal 1: feature server
cd /path/to/feature_repo
feast apply && feast materialize 2025-01-01T00:00:00 2027-01-01T00:00:00
feast serve --port 6566

# Terminal 2: MCP server (the thing you're developing)
feast-mcp --feast-url http://localhost:6566 --transport sse --port 8000

# ...or, to exercise OIDC with a shared OAuth-state store (load-balancer safe):
feast-mcp --feast-url http://localhost:6566 --transport http --port 8000 \
  --auth-mode oidc \
  --oidc-discovery-url http://localhost:8081/.well-known/openid-configuration \
  --oidc-client-id feast-mcp \
  --session-storage-backend redis   # options via feast_mcp.yaml session_storage.options

# Terminal 3: run tests against them
FEAST_FEATURE_SERVER_URL=http://localhost:6566 \
FEAST_MCP_SERVER_URL=http://localhost:8000 \
  make test-feature-server
```

Now you can make changes to the MCP server, restart it in terminal 2,
and re-run the tests in terminal 3 without waiting for feast apply /
materialize every time.

### Example: test only the registry

```bash
# Terminal 1
feast serve_registry --rest-api --port 6570 --rest-port 6572

# Terminal 2
FEAST_REGISTRY_SERVER_URL=http://localhost:6572/api/v1 \
FEAST_MCP_SERVER_URL=http://localhost:8000 \
  make test-registry
```

## Directory Structure

```
MCP/tests/
  conftest.py               Fixtures: server lifecycle, REST/MCP helpers, auth
  manifest.py               ToolTestSpec dataclass + 78 tool definitions
  migration_report.py       Pytest plugin printing the migration checklist
  test_discovery.py         Coverage cross-check (OpenAPI vs manifest)
  test_feature_server.py    Parametrized over 11 feature server tools
  test_registry_server.py   Parametrized over 67 registry tools
  test_authorization.py     Auth cases (401/403/200) for both servers
  feature_repo/
    feature_store.yaml      SQLite online store + file registry + MCP enabled
    definitions.py          Entity, FeatureView, PushSource, FeatureService
    permissions.py          Admin + reader RBAC permissions
    data/
      driver_stats.parquet  20 rows of test data (driver_ids 1001-1020)
```

## How It Works

### The Manifest (`manifest.py`)

Every MCP tool is defined as a `ToolTestSpec` dataclass:

```python
@dataclass(frozen=True)
class ToolTestSpec:
    tool_name: str                         # MCP tool name
    feast_endpoint: str                    # REST path
    http_method: HttpMethod                # GET, POST, DELETE (enum)
    server_type: ServerType                # FEATURE_SERVER or REGISTRY (enum)
    sample_inputs: list[dict[str, Any]]    # Valid payloads for testing
    migrated: bool = False                 # Flip when implemented in new MCP SDK
    mutation: bool = False                 # True for write operations
    verify_endpoint: str | None = None     # Read endpoint to check side effects
    verify_expected: dict[str, Any] | None = None
```

Two lists hold all definitions:
- `FEATURE_SERVER_TOOLS` -- 11 entries (get_online_features, push, search, health, etc.)
- `REGISTRY_TOOLS` -- 67 entries (entities CRUD, feature_views CRUD, lineage, metrics, etc.)

### Test Behavior

| `migrated` | `mutation` | What the test does |
|---|---|---|
| `False` | `False` | Calls REST endpoint only, asserts 2xx (baseline) |
| `False` | `True` | Calls REST endpoint only, asserts 2xx (baseline) |
| `True` | `False` | Calls REST + MCP, asserts exact match after normalization |
| `True` | `True` | Calls MCP, asserts success, verifies side effect via read endpoint |

### Coverage Cross-Check

`test_discovery.py` compares two sources of truth:
- **Auto-discovered endpoints** from `/openapi.json` (what the server actually exposes)
- **Hand-written manifest** (the `ToolTestSpec` list)

Gaps produce **warnings**, not failures, so they don't block CI.

### Server Lifecycle

All tests use real servers started as subprocesses (not in-process TestClient):

```
feature_repo_path  (feast apply + materialize into temp dir)
    |-- feature_server   (feast serve on port A)
    |-- registry_server  (feast serve_registry --rest-api on port B)
    |-- mcp_server       (feast-mcp --feast-url http://localhost:A on port C)

mock_oidc_server  (mock OIDC provider on random port)
    |-- auth_feature_repo_path  (feature repo with OIDC config)
        |-- auth_feature_server   (feast serve with auth)
        |-- auth_registry_server  (feast serve_registry with auth)
```

The MCP server is a standalone process that proxies to the feature server. It is NOT mounted at `/mcp` on the feature server.

All fixtures are session-scoped (started once, shared across all tests).

### Migration Report

Printed automatically after every `pytest` run:

```
=== FEAST MCP MIGRATION STATUS ===

FEATURE SERVER (0/11 migrated)
------------------------------------------------------------------------
  [ ] get_online_features             -> POST   /get-online-features    (not migrated)
  [ ] push                            -> POST   /push                   (not migrated)
  ...

REGISTRY SERVER (0/67 migrated)
------------------------------------------------------------------------
  [ ] list_entities                   -> GET    /api/v1/entities        (not migrated)
  ...

TOTAL: 0/78 migrated (0.0%)
```

Three states per tool:
- `[ ]` not migrated (only REST baseline ran)
- `[+]` PASS (migrated, MCP output matched REST)
- `[X]` FAIL (migrated, comparison failed)

## How to Migrate a Tool

1. Implement the tool in the new MCP SDK server
2. In `manifest.py`, find the corresponding `ToolTestSpec` and set `migrated=True`
3. Run `pytest MCP/tests/ -v`
4. The test will now call both REST and MCP, compare outputs, and report pass/fail

## Adding a New Endpoint

When a new endpoint is added to the Feast feature server or registry:

1. `test_discovery.py` will warn about the uncovered endpoint
2. Add a `ToolTestSpec` entry to `FEATURE_SERVER_TOOLS` or `REGISTRY_TOOLS` in `manifest.py`
3. Include at least one `sample_input` with realistic data that references the test feature repo

## Test Data

The test feature repo contains:
- **Entity**: `driver` (join_key: `driver_id`)
- **FeatureView**: `driver_hourly_stats` with `conv_rate`, `acc_rate`, `avg_daily_trips`
- **FeatureService**: `driver_activity`
- **PushSource**: `driver_stats_push`
- **Data**: 20 rows for driver_ids 1001-1020 with deterministic values

## Authorization Testing

Uses the mock OIDC server from `examples/mcp_auth_feature_store/mock_oidc_server.py`.

Three hardcoded users:
- `admin` (role: `["admin"]`) -- full access
- `reader` (role: `["reader"]`) -- describe + read online only
- `user` (role: `["user"]`) -- no matching permission, gets 403

Test cases:
- No `Authorization` header -> 401
- Invalid/expired JWT -> 401
- Valid token, wrong role -> 403
- Valid token, correct role -> 200

### Session storage (load-balanced OIDC)

The OIDC OAuth flow spans multiple requests (`/authorize` -> IdP ->
`/callback` -> `/token`) whose state the proxy correlates via a
`key_value.aio` store. Behind a load balancer with more than one replica
that store must be **shared**, or a `/callback` can land on a replica that
never saw the matching `/authorize`. Select a shared backend with
`--session-storage-backend` (or `FEAST_MCP_SESSION_STORAGE_BACKEND`):

```bash
# Redis-backed OAuth state, safe across replicas
feast-mcp ... --auth-mode oidc --session-storage-backend redis
```

Backends: `redis`, `valkey`, `postgresql`, `mongodb`, `disk`, `memory`
(from `py-key-value-aio`; install the matching extra, e.g.
`pip install 'py-key-value-aio[redis]'`). Connection options go in
`feast_mcp.yaml` under `session_storage.options`. `memory` and `disk` are
node-local and log a warning when selected.
