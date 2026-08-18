# Feast MCP Server — OpenTelemetry (OTEL) Demo

End-to-end example of exporting `feast-mcp` logs to an OpenTelemetry
Collector and viewing them in a **web UI** (OpenObserve). Logs always go to
the console (stderr); when an OTLP endpoint is configured, the **same** log
lines are *also* exported over OTLP.

## Architecture

```
feast-mcp server ── logs ──> console (stderr)                     # always
        │
        └──────── OTLP ─────> OpenTelemetry Collector ──┬──> debug (prints to stdout)
                  4317/gRPC                              │
                  4318/HTTP                              └──> OpenObserve ──> UI
                                                              (stores logs)   http://localhost:5080
```

## Where do I see the logs in a UI?

Open **http://localhost:5080** once the stack is up and log in with:

| Field    | Value               |
|----------|---------------------|
| Email    | `root@example.com`  |
| Password | `Complexpass@123`   |

Then go to **Logs**, pick the `default` stream, and you'll see each exported
record — filterable and searchable. (There's a short delay: the Collector
batches records before shipping them, so give it a few seconds after the
first log line.)

## What's in here

```
otel_demo/
  README.md                    this file
  docker-compose.yaml          runs the Collector + OpenObserve (UI)
  otel-collector-config.yaml   Collector config (OTLP in -> debug + OpenObserve)
  run_demo.sh                  one command to run the whole demo
  demo_client.py               test client that calls tools to generate logs
  setup_data.py                generates sample data + applies the registry
  feature_repo/                a real, self-contained Feast repo (no auth)
    feature_store.yaml
    features.py
```

## Prerequisites

- Docker (for the Collector + OpenObserve) — or run your own however you like.
- Feast installed (`pip install feast`) to run the bundled feature server.
- The OTEL extra installed:

  ```bash
  pip install 'feast-mcp[otel]'
  ```

  Without it, `feast-mcp` logs a warning and keeps logging to the console
  only (it does **not** crash).

## Quick start

```bash
cd MCP/examples/otel_demo
./run_demo.sh
```

The script starts the Collector + OpenObserve, sets up sample data, starts a
real Feast feature server, starts `feast-mcp` with OTLP export on, and tails
the Collector so you can watch the exported records. Then open the UI at
**http://localhost:5080** to browse them. Stop with Ctrl-C.

## Manual setup

```bash
# 1. Start the Collector + OpenObserve UI
docker compose up -d
docker compose logs -f otel-collector      # in a second terminal (optional)

# 2. Set up sample data and apply the Feast registry
python setup_data.py

# 3. Start the Feast feature server
cd feature_repo && feast serve --host 0.0.0.0 --port 6566 &
cd ..

# 4. Start feast-mcp with OTLP export enabled
feast-mcp \
  --feast-url http://localhost:6566 \
  --transport http --port 8000 \
  --log-level INFO \
  --log-format json \
  --otel-endpoint http://localhost:4317
```

Setting `--otel-endpoint` turns export on automatically — there is no
separate "enabled" switch.

## Make a request (generate log traffic)

With the feature server running, any MCP call flows through the server's
`get_auth_token()` and produces a per-request log line (exported to OTEL too).
Use the bundled `demo_client.py` to fire some calls:

```bash
# one pass over the sample tool calls
python demo_client.py

# keep calling to produce a steady stream you can watch in the UI
python demo_client.py --loop --interval 2
```

Each call produces a line like `Unauthenticated request: ip=... request=POST
/mcp` (the request is unauthenticated because this repo has no auth) in the
console, the Collector, and the OpenObserve UI.

Other options:

```bash
python demo_client.py --mcp-url http://localhost:8000   # different server URL
python demo_client.py --token <jwt>                     # send a bearer token
```

## What you should see

Two copies of each log line:

1. **In the `feast-mcp` terminal** (console / stderr), e.g.:

   ```json
   {"timestamp": "...", "level": "INFO", "logger": "feast_mcp.server", "message": "OTEL log export enabled -> http://localhost:4317 (grpc)"}
   ```

2. **In the Collector output** (`docker compose logs -f otel-collector`), the
   same message arriving as an OTLP `LogRecord`:

   ```
   LogRecord #0
   Body: Str(OTEL log export enabled -> http://localhost:4317 (grpc))
   SeverityText: INFO
   ...
   ```

3. **In the OpenObserve UI** at http://localhost:5080 → **Logs** → `default`
   stream: the same records, searchable and filterable.

See [Make a request](#make-a-request) above to also produce per-request auth
log lines.

## Correlating logs for one request (trace ids)

`feast-mcp` opens an OpenTelemetry span per HTTP request, so **every** log line
produced while handling that request shares one `trace_id`. Fire a request and
you'll see the same id on all of its lines:

```json
{"level": "INFO", "logger": "feast_mcp.auth", "message": "Unauthenticated request: ip=127.0.0.1 request=POST /mcp", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7"}
```

- **In the UI**, filter the `default` logs stream by that `trace_id` to see the
  whole request's logs together.
- The spans are exported too — open the **Traces** view (also the `default`
  stream) to see the request as a trace and jump between the trace and its logs.

> Trace correlation needs the OTEL SDK (`pip install 'feast-mcp[otel]'`).
> Without it, `feast-mcp` still tags each request's logs with a generated id so
> they stay groupable on the console — but no real trace id or spans are
> exported.

## Using the HTTP protocol instead of gRPC

The Collector in this demo listens on both. To export over HTTP, point at the
4318 port and select the `http` protocol:

```bash
feast-mcp \
  --feast-url http://localhost:6566 \
  --transport http --port 8000 \
  --otel-endpoint http://localhost:4318 \
  --otel-protocol http
```

## Configuring via environment variables or YAML

Anything you can pass as a flag also works as an env var or in
`feast_mcp.yaml`. Standard `OTEL_*` variables are honored as a fallback, so
existing OpenTelemetry tooling works unchanged.

```bash
export FEAST_MCP_OTEL_ENDPOINT=http://localhost:4317
export FEAST_MCP_OTEL_PROTOCOL=grpc
export FEAST_MCP_OTEL_SERVICE_NAME=feast-mcp
export FEAST_MCP_LOG_FORMAT=json
feast-mcp --feast-url http://localhost:6566 --transport http --port 8000
```

```yaml
# feast_mcp.yaml
observability:
  level: INFO
  format: json
  otel_endpoint: http://localhost:4317
  otel_protocol: grpc          # grpc | http
  otel_service_name: feast-mcp
```

## Sending to a managed backend (auth headers)

The demo Collector needs no credentials. Managed backends (Grafana Cloud,
Honeycomb, New Relic, Datadog, …) require an API token, passed as **OTLP
headers** as `key=value` pairs separated by commas:

```bash
export FEAST_MCP_OTEL_ENDPOINT=https://otlp.example-backend.com
export FEAST_MCP_OTEL_HEADERS="authorization=Bearer <token>,x-scope-orgid=team-a"
feast-mcp --feast-url http://localhost:6566 --transport http --port 8000
```

These headers authenticate the **server → collector/backend** connection.
They are unrelated to the caller's bearer token that MCP forwards to Feast.
Because they usually hold a secret, prefer an environment variable (or a
Kubernetes Secret → env var) over committing them to `feast_mcp.yaml`.

## Cleanup

```bash
docker compose down       # stop the Collector + OpenObserve
docker compose down -v    # also delete the stored logs (openobserve-data volume)
```
