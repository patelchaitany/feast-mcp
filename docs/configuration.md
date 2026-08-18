# Configuration

This page lists everything you can configure and how to set it.

## Three ways to set anything

You can configure the server in three places. If the same setting is given in
more than one place, the one higher in this list wins:

1. **Command-line flags** — e.g. `--feast-url http://localhost:6566`
2. **Environment variables** — e.g. `FEAST_MCP_FEATURE_SERVER_URL=...`
3. **A YAML file** — `feast_mcp.yaml` in the current folder, or `--config path.yaml`

So a flag always beats an environment variable, which always beats the YAML
file, which beats the built-in default.

Copy `feast_mcp.yaml.example` to `feast_mcp.yaml` to get started with the file.

## Required: at least one upstream URL

The server needs to know where your Feast servers are. You must give at least
one of these, or it will refuse to start:

| What | Flag | Environment variable | YAML |
|---|---|---|---|
| Feature server | `--feast-url` | `FEAST_MCP_FEATURE_SERVER_URL` | `features.url` |
| Registry server | `--registry-url` | `FEAST_MCP_REGISTRY_URL` | `registry.url` |

- Give **both** to expose all 22 tools.
- Give only one to expose just that half.

## Transport: how clients connect

The transport decides how the server talks to clients.

| Transport | Use it for | Client connects with |
|---|---|---|
| `stdio` (default) | Local IDE use — the client launches the server | a command, not a URL |
| `http` / `streamable-http` | A running network service | `http://host:port/mcp` |
| `sse` | Older clients that need Server-Sent Events | `http://host:port/sse` |

| Setting | Flag | Environment variable | YAML | Default |
|---|---|---|---|---|
| Transport | `--transport` | `FEAST_MCP_TRANSPORT` | `server.transport` | `stdio` |
| Host | `--host` | *(none)* | `server.host` | `0.0.0.0` |
| Port | `--port` | *(none)* | `server.port` | `8000` |
| Workers | `--workers` | `FEAST_MCP_WORKERS` | `server.workers` | 1 (single process) |

Notes:
- `host` and `port` can only be set with a flag or in YAML — there is no
  environment variable for them.
- `workers` above 1 runs the server with **gunicorn** (multiple processes).
  With 1 (or unset) it runs with **uvicorn** (single process).
- Multiple workers do **not** work with the `sse` transport. Use `http` if you
  need more than one worker.

## Timeout

How long to wait for the upstream Feast servers to respond.

| Setting | Flag | Environment variable | YAML | Default |
|---|---|---|---|---|
| Timeout (seconds) | `--timeout` | `FEAST_MCP_TIMEOUT` | `timeout` | `30` |

## Authentication

The MCP server does **not** check tokens itself. It passes the caller's
`Authorization: Bearer <token>` header straight through to Feast, which does the
real validation and permission checks.

There are two modes:

| Mode | What it does |
|---|---|
| `passthrough` (default) | No login. The client is expected to already have a token. |
| `oidc` | The server runs a browser login flow so IDE clients can sign the user in. |

| Setting | Flag | Environment variable | YAML |
|---|---|---|---|
| Mode | `--auth-mode` | `FEAST_MCP_AUTH_MODE` | `auth.mode` |
| Discovery URL | `--oidc-discovery-url` | `FEAST_MCP_OIDC_DISCOVERY_URL` | `auth.discovery_url` |
| Client ID | `--oidc-client-id` | `FEAST_MCP_OIDC_CLIENT_ID` | `auth.client_id` |
| Client secret | `--oidc-client-secret` | `FEAST_MCP_OIDC_CLIENT_SECRET` | `auth.client_secret` |
| Audience | `--oidc-audience` | `FEAST_MCP_OIDC_AUDIENCE` | `auth.audience` |
| Public base URL | `--base-url` | `FEAST_MCP_BASE_URL` | `auth.base_url` |

When `auth.mode` is `oidc`, you **must** provide the discovery URL and the
client ID, or the server won't start.

### Session storage (only needed for OIDC behind a load balancer)

The OIDC login is a multi-step handshake. The server has to remember some state
between the steps (which login is in progress, the codes it handed out, and so
on). By default this state is kept on the local disk of one process.

That's fine for a single instance. But if you run **more than one copy** of the
server behind a load balancer, a later step of the login can land on a copy that
doesn't have the earlier state — and the login fails. The fix is to keep that
state in a **shared** store that every copy can reach (like Redis).

| Setting | Flag | Environment variable | YAML |
|---|---|---|---|
| Backend | `--session-storage-backend` | `FEAST_MCP_SESSION_STORAGE_BACKEND` | `session_storage.backend` |
| Backend options | *(none)* | *(none)* | `session_storage.options` |

Supported backends: `redis`, `valkey`, `postgresql`, `mongodb`, `disk`,
`memory`. `memory` and `disk` are **not** shared between processes, so the
server warns you if you pick them.

Each backend needs its own extra package, for example:

```bash
pip install 'py-key-value-aio[redis]'
```

Example in `feast_mcp.yaml`:

```yaml
session_storage:
  backend: redis
  options:
    url: redis://localhost:6379
```

The `options` are passed straight to the backend, so use whatever that backend
expects (for Redis, either a `url`, or `host` + `port` + `db`).

## Logging and OpenTelemetry (OTEL)

Logs always go to the console (on **stderr**, because the `stdio` transport
needs stdout for the protocol). If you also give an OTLP endpoint, the same log
lines are **exported to OpenTelemetry** as well.

OTEL export needs an extra package:

```bash
pip install 'feast-mcp[otel]'
```

| Setting | Flag | Environment variable | YAML | Default |
|---|---|---|---|---|
| Log level | `--log-level` | `FEAST_MCP_LOG_LEVEL` | `observability.level` | `INFO` |
| Log format | `--log-format` | `FEAST_MCP_LOG_FORMAT` | `observability.format` | `text` |
| Console on/off | *(none)* | `FEAST_MCP_LOG_STDIO` | `observability.stdio` | `true` |
| OTLP endpoint | `--otel-endpoint` | `FEAST_MCP_OTEL_ENDPOINT` | `observability.otel_endpoint` | *(none)* |
| Protocol | `--otel-protocol` | `FEAST_MCP_OTEL_PROTOCOL` | `observability.otel_protocol` | `grpc` |
| Service name | `--otel-service-name` | `FEAST_MCP_OTEL_SERVICE_NAME` | `observability.otel_service_name` | `feast-mcp` |
| OTLP headers | *(none)* | `FEAST_MCP_OTEL_HEADERS` | `observability.otel_headers` | *(none)* |

Notes:
- Setting an OTLP endpoint turns OTEL on automatically. You don't need a
  separate "enabled" switch.
- Log format can be `text` (easy to read) or `json` (easy for machines).
- Logs from FastMCP, the MCP SDK, and the web server (uvicorn / gunicorn) are
  **bridged** onto the same handlers, so their output shows up on the console
  and in OpenTelemetry too — not just the server's own logs.
- Every request is logged with its auth context: the user (from the token),
  the client IP (using `X-Forwarded-For` / `X-Real-IP` when behind a proxy),
  and the request method and path. This happens at the `INFO` level.
- Each HTTP request is wrapped in an OpenTelemetry span, so all log lines for
  one request share a `trace_id` (shown as `[trace=…]` in text logs and a
  `trace_id` field in JSON logs) — making it easy to group a single request's
  logs. With the OTEL SDK installed it's a real trace id and the span is
  exported too; without it, a generated per-request id keeps console logs
  groupable.
- The standard OpenTelemetry variables also work as a fallback:
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`,
  `OTEL_SERVICE_NAME`, and `OTEL_EXPORTER_OTLP_HEADERS`.
- If you ask for OTEL but the package isn't installed, the server prints a
  warning and keeps logging to the console.

## A full YAML example

```yaml
server:
  transport: http
  host: 0.0.0.0
  port: 8000
  workers: 4

features:
  url: http://localhost:6566

registry:
  url: http://localhost:8080

timeout: 30

auth:
  mode: oidc
  discovery_url: https://keycloak.example.com/realms/feast/.well-known/openid-configuration
  client_id: feast-mcp
  base_url: https://mcp.example.com:8000

session_storage:
  backend: redis
  options:
    url: redis://localhost:6379

observability:
  level: INFO
  format: json
  otel_endpoint: http://localhost:4317
  otel_service_name: feast-mcp
```
