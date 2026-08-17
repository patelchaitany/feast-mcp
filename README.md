# Feast MCP Server

Standalone MCP server for Feast, built on [FastMCP](https://gofastmcp.com/).

Composes two namespaced sub-servers behind a single MCP endpoint:

- **features** — proxies to the Feast feature server (online features, vector search, push, materialization). Mounted when `--feast-url` is provided.
- **registry** — proxies to the Feast REST registry server (browse feature views, entities, data sources, lineage). Mounted when `--registry-url` is provided.

The caller's `Authorization: Bearer <token>` header is passed through so that upstream servers handle OIDC / Kubernetes RBAC as usual.

## Documentation

Full guides live in [`docs/`](docs/README.md):

- [Configuration](docs/configuration.md) — every setting and how to set it
- [Deployment](docs/deployment.md) — running locally, with Docker, and on Kubernetes
- [Development](docs/development.md) — changing the code, tests, and adding tools

## Quick start

```bash
cd MCP
pip install -e .

# Feature server only (9 tools)
feast-mcp --feast-url http://localhost:6566

# Registry only (13 tools)
feast-mcp --registry-url http://localhost:8080

# Both (22 tools)
feast-mcp --feast-url http://localhost:6566 --registry-url http://localhost:8080

# HTTP transport on a custom port
feast-mcp --feast-url http://localhost:6566 --transport http --port 8000
```

Environment variables work too:

```bash
export FEAST_MCP_FEATURE_SERVER_URL=http://localhost:6566
export FEAST_MCP_REGISTRY_URL=http://localhost:8080
feast-mcp
```

## Tools exposed

### Feature server tools (`features_` prefix)

| Tool | Upstream endpoint | Description |
|---|---|---|
| `features_get_online_features` | `POST /get-online-features` | Retrieve online feature values |
| `features_search` | `POST /search` | Vector similarity search |
| `features_list_vector_stores` | `GET /v1/vector_stores` | List vector stores |
| `features_get_vector_store` | `GET /v1/vector_stores/{id}` | Get a vector store |
| `features_vector_store_search` | `POST /v1/vector_stores/{id}/search` | OpenAI-compatible vector search |
| `features_push` | `POST /push` | Push features to the store |
| `features_materialize` | `POST /materialize` | Materialize features |
| `features_materialize_incremental` | `POST /materialize-incremental` | Incremental materialization |
| `features_health` | `GET /health` | Health check |

### Registry tools (`registry_` prefix)

| Tool | Upstream endpoint | Description |
|---|---|---|
| `registry_list_projects` | `GET /api/v1/projects` | List all projects |
| `registry_get_project` | `GET /api/v1/projects/{name}` | Get project details |
| `registry_list_entities` | `GET /api/v1/entities` | List entities in a project |
| `registry_get_entity` | `GET /api/v1/entities/{name}` | Get entity details |
| `registry_list_feature_views` | `GET /api/v1/feature_views` | List all feature views |
| `registry_get_feature_view` | `GET /api/v1/feature_views/{name}` | Get feature view details |
| `registry_list_features` | `GET /api/v1/features` | List individual features |
| `registry_list_feature_services` | `GET /api/v1/feature_services` | List feature services |
| `registry_get_feature_service` | `GET /api/v1/feature_services/{name}` | Get feature service details |
| `registry_list_data_sources` | `GET /api/v1/data_sources` | List data sources |
| `registry_get_data_source` | `GET /api/v1/data_sources/{name}` | Get data source details |
| `registry_search_registry` | `GET /api/v1/search` | Full-text search across registry |
| `registry_get_lineage` | `GET /api/v1/lineage/complete` | Get lineage relationships |

## Project structure

```
feast_mcp/
  server.py         — composition + CLI entry point
  features.py       — feature server tools (9 tools)
  registry.py       — registry server tools (13 tools)
  client.py         — shared HTTP client
  auth.py           — shared auth helpers
  session_storage/  — factory for the shared OAuth-state store (key_value.aio)
  observability/    — logging fanned out to stdout + OpenTelemetry
```

## Authorization

The MCP server itself does **not** validate tokens. It forwards the bearer token from the MCP request context to the upstream servers, which perform OIDC or Kubernetes token validation and RBAC enforcement.

For OIDC browser-based login:

```bash
feast-mcp \
  --feast-url http://localhost:6566 \
  --auth-mode oidc \
  --oidc-discovery-url https://keycloak.example.com/realms/feast/.well-known/openid-configuration \
  --oidc-client-id feast-mcp \
  --transport http --port 8000
```

### Session storage (load-balanced OIDC)

The OIDC OAuth flow is a multi-request handshake (`/authorize` → IdP →
`/callback` → `/token`), and the proxy correlates those requests through
server-side state: client registrations, in-flight transactions,
authorization codes, and token mappings. By default this state lives in an
**on-disk, per-node** store, so behind a load balancer with more than one
replica a `/callback` can hit a replica that never saw the matching
`/authorize` — and the login fails.

Point the proxy at a **shared** backend to make the flow load-balancer safe.
Backends are provided by [`py-key-value-aio`](https://pypi.org/project/py-key-value-aio/):
`redis`, `valkey`, `postgresql`, `mongodb`, `disk`, `memory`.

```bash
feast-mcp \
  --feast-url http://localhost:6566 \
  --auth-mode oidc \
  --oidc-discovery-url https://keycloak.example.com/realms/feast/.well-known/openid-configuration \
  --oidc-client-id feast-mcp \
  --session-storage-backend redis \
  --transport http --port 8000
```

The backend can also be set via `FEAST_MCP_SESSION_STORAGE_BACKEND`.
Backend-specific connection options go in `feast_mcp.yaml` under
`session_storage.options` and are passed through to the underlying store:

```yaml
session_storage:
  backend: redis          # redis | valkey | postgresql | mongodb | disk | memory
  options:
    url: redis://localhost:6379
```

Install the extra for your chosen backend, e.g.
`pip install 'py-key-value-aio[redis]'`. When no backend is configured, the
proxy falls back to FastMCP's default on-disk store (fine for a single
replica). `memory` and `disk` are **not** shared across processes — the
server logs a warning if you select them.

## Observability (logging + OpenTelemetry)

Logs always go to the console (stderr — stdout is reserved by the MCP stdio
transport). When an OTLP endpoint is configured, the **same** log lines are
*also* exported to your OpenTelemetry backend for visibility.

FastMCP, the MCP SDK, and the web server (uvicorn / gunicorn) log to their own
logger trees. Those are **bridged** onto the same handlers, so their output
lands on the console *and* in OpenTelemetry alongside the server's own logs —
you don't lose framework logs.

Every tool call passes through `get_auth_token()`, which logs one line of auth
context per request: the authenticated **user** (from the token claims —
`preferred_username`/`email`/`sub` and `client_id`), the client **IP**
(honoring `X-Forwarded-For` / `X-Real-IP` behind a proxy), and the **request**
(`METHOD /path`). Unauthenticated requests are logged too. Example:

```
INFO feast_mcp.auth: Authenticated request: user=alice (client_id=feast-mcp) ip=10.0.0.7 request=POST /mcp
```

OTEL export is optional — install the extra:

```bash
pip install 'feast-mcp[otel]'
```

Enable it by pointing at an OTLP collector:

```bash
feast-mcp \
  --feast-url http://localhost:6566 \
  --log-level INFO \
  --log-format json \
  --otel-endpoint http://localhost:4317 \
  --transport http --port 8000
```

Setting `--otel-endpoint` turns export on automatically. Configuration
resolves from CLI args, then environment variables, then `feast_mcp.yaml`:

| Setting | CLI | Env var | Default |
|---|---|---|---|
| Log level | `--log-level` | `FEAST_MCP_LOG_LEVEL` | `INFO` |
| Log format (`text`/`json`) | `--log-format` | `FEAST_MCP_LOG_FORMAT` | `text` |
| Console logging | — | `FEAST_MCP_LOG_STDIO` | `true` |
| OTLP endpoint | `--otel-endpoint` | `FEAST_MCP_OTEL_ENDPOINT` / `OTEL_EXPORTER_OTLP_ENDPOINT` | — |
| Protocol (`grpc`/`http`) | `--otel-protocol` | `FEAST_MCP_OTEL_PROTOCOL` / `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` |
| Service name | `--otel-service-name` | `FEAST_MCP_OTEL_SERVICE_NAME` / `OTEL_SERVICE_NAME` | `feast-mcp` |
| OTLP headers | — | `FEAST_MCP_OTEL_HEADERS` / `OTEL_EXPORTER_OTLP_HEADERS` | — |

Standard `OTEL_*` variables are honored as a fallback, so existing
OpenTelemetry tooling works unchanged. Equivalent `feast_mcp.yaml`:

```yaml
observability:
  level: INFO
  format: json
  stdio: true
  otel_endpoint: http://localhost:4317
  otel_protocol: grpc       # grpc | http
  otel_service_name: feast-mcp
```

If OTEL is requested but the SDK/exporter isn't installed, the server logs a
warning and continues with console logging only.

## IDE / client configuration

### Local (client launches `feast-mcp` over stdio)

The client starts the server as a subprocess and talks to it over stdio — no
port, no running server to manage:

```json
{
  "mcpServers": {
    "feast": {
      "command": "feast-mcp",
      "args": [
        "--feast-url", "http://localhost:6566",
        "--registry-url", "http://localhost:8080"
      ]
    }
  }
}
```

Feature server only:

```json
{
  "mcpServers": {
    "feast": {
      "command": "feast-mcp",
      "args": ["--feast-url", "http://localhost:6566"]
    }
  }
}
```

Registry only:

```json
{
  "mcpServers": {
    "feast": {
      "command": "feast-mcp",
      "args": ["--registry-url", "http://localhost:8080"]
    }
  }
}
```

### Remote (paste a URL — no local command)

When the server is already running over HTTP (started with `--transport http`
or deployed behind a load balancer), the client doesn't launch anything — just
point it at the URL. Nothing is installed locally.

The endpoint depends on the transport the server was started with:

| Server transport | Endpoint to paste |
|---|---|
| `http` / `streamable-http` | `http://<host>:<port>/mcp` |
| `sse` | `http://<host>:<port>/sse` |

```json
{
  "mcpServers": {
    "feast": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

For a deployed server, use its public URL (HTTPS recommended):

```json
{
  "mcpServers": {
    "feast": {
      "url": "https://feast-mcp.example.com/mcp"
    }
  }
}
```

If the server runs with `--auth-mode oidc`, the client performs the browser
login automatically on first connect. For a server that expects a bearer
token directly, clients that support custom headers can send one:

```json
{
  "mcpServers": {
    "feast": {
      "url": "https://feast-mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

> Some clients name the fields differently (e.g. `"type": "http"` /
> `"transport": "sse"`). Check your client's MCP docs if `url` alone isn't
> recognized.
