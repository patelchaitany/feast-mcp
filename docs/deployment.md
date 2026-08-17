# Deployment

This page shows how to run the server for real: on your machine, in a
container, and on Kubernetes.

Before you start, make sure your Feast servers are already running and reachable.
The MCP server only forwards requests to them:

```bash
# Feature server
feast serve --port 6566

# Registry server (REST API)
feast serve_registry --rest-api --port 6570 --rest-port 8080
```

## Pick a transport first

How you run the server depends on how clients will connect.

- **stdio** — the client (an IDE) starts the server for you. You don't "deploy"
  anything; you just tell the client the command to run. See the main README's
  "IDE / client configuration" section.
- **http** — the server runs as a long-lived network service. This is what you
  use for a shared or production deployment. The rest of this page is about this
  mode.

## Run it directly (simplest)

```bash
pip install -e .

feast-mcp \
  --feast-url http://localhost:6566 \
  --registry-url http://localhost:8080 \
  --transport http \
  --host 0.0.0.0 \
  --port 8000
```

Clients now connect to `http://<host>:8000/mcp`.

### More than one worker

For more traffic, run several worker processes. This switches the server to
gunicorn automatically:

```bash
pip install -e '.[server]'   # installs gunicorn + uvicorn

feast-mcp \
  --feast-url http://localhost:6566 \
  --transport http \
  --port 8000 \
  --workers 4
```

Multiple workers need the `http` transport (not `sse`).

## Use a YAML config file

Instead of passing lots of flags or environment variables, you can put all your
settings in one YAML file. This is the easiest way to manage a real deployment.

Reading a YAML file needs the `yaml` extra:

```bash
pip install 'feast-mcp[yaml]'
```

Start from the example file and edit it:

```bash
cp feast_mcp.yaml.example feast_mcp.yaml
```

The server picks up the file in two ways:

1. **Automatically** — if a file named `feast_mcp.yaml` (or `feast_mcp.yml`) is
   in the folder you run the command from:

   ```bash
   feast-mcp
   ```

2. **Explicitly** — point at any path with `--config`:

   ```bash
   feast-mcp --config /etc/feast-mcp/feast_mcp.yaml
   ```

A complete `feast_mcp.yaml` looks like this:

```yaml
server:
  transport: http
  host: 0.0.0.0
  port: 8000

features:
  url: http://localhost:6566

registry:
  url: http://localhost:8080

timeout: 30
```

Remember the priority order: a **flag** beats an **environment variable**, which
beats the **YAML file**. So you can keep shared settings in YAML and still
override one value with a flag when you need to:

```bash
feast-mcp --config feast_mcp.yaml --port 9000
```

See [configuration.md](configuration.md) for every setting you can put in the
file.

## Run it with Docker / Podman

Build the image:

```bash
make build-image                 # uses Containerfile
# or: docker build -f Containerfile -t feast-mcp .
```

Run it, passing configuration as environment variables:

```bash
docker run --rm -p 8000:8000 \
  -e FEAST_MCP_FEATURE_SERVER_URL=http://feature-server:6566 \
  -e FEAST_MCP_REGISTRY_URL=http://registry-server:8080 \
  -e FEAST_MCP_TRANSPORT=http \
  --entrypoint feast-mcp \
  feast-mcp
```

> **Note:** the default command in `Containerfile` starts gunicorn with an ASGI
> module (`feast_mcp.asgi:app`) that is not included yet. Until that module is
> added, run the CLI directly with `--entrypoint feast-mcp` as shown above.

### Passing a YAML file into the container

Mount your `feast_mcp.yaml` into the container and point `--config` at it:

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/feast_mcp.yaml:/config/feast_mcp.yaml:ro" \
  --entrypoint feast-mcp \
  feast-mcp --config /config/feast_mcp.yaml
```

The image must have the `yaml` extra installed. If you build your own image, add
`pyyaml` (or install `.[yaml]`) so the file can be read.

## Run it on Kubernetes

A minimal Deployment and Service:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: feast-mcp
spec:
  replicas: 2
  selector:
    matchLabels: { app: feast-mcp }
  template:
    metadata:
      labels: { app: feast-mcp }
    spec:
      containers:
        - name: feast-mcp
          image: feast-mcp:latest
          command: ["feast-mcp"]           # until an ASGI module ships
          ports:
            - containerPort: 8000
          env:
            - name: FEAST_MCP_FEATURE_SERVER_URL
              value: http://feature-server:6566
            - name: FEAST_MCP_REGISTRY_URL
              value: http://registry-server:8080
            - name: FEAST_MCP_TRANSPORT
              value: http
          livenessProbe:
            tcpSocket: { port: 8000 }
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            tcpSocket: { port: 8000 }
            initialDelaySeconds: 5
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: feast-mcp
spec:
  selector: { app: feast-mcp }
  ports:
    - port: 80
      targetPort: 8000
```

### Using a YAML file on Kubernetes

Put the YAML in a ConfigMap, mount it into the pod, and point `--config` at the
mounted path. This keeps all settings in one place.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: feast-mcp-config
data:
  feast_mcp.yaml: |
    server:
      transport: http
      host: 0.0.0.0
      port: 8000
    features:
      url: http://feature-server:6566
    registry:
      url: http://registry-server:8080
```

Then mount it in the Deployment (changes to the container spec above):

```yaml
      containers:
        - name: feast-mcp
          image: feast-mcp:latest
          command: ["feast-mcp", "--config", "/config/feast_mcp.yaml"]
          ports:
            - containerPort: 8000
          volumeMounts:
            - name: config
              mountPath: /config
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: feast-mcp-config
```

Keep secrets (like an OIDC client secret) out of the ConfigMap. Put those in a
Kubernetes Secret and pass them as environment variables instead — remember an
environment variable overrides the YAML file.

## Running more than one copy (load balancing)

If you run **several copies** of the server behind a load balancer, there are
two things to keep in mind.

### 1. MCP sessions are tied to one copy

In `http` mode the server keeps each client's MCP session in memory. A follow-up
request must reach the **same copy** that started the session, or it will be
rejected. So turn on **session affinity** (sticky sessions) at the load
balancer, keyed on the client connection or the `Mcp-Session-Id`.

For a Kubernetes Service, the simple version is:

```yaml
spec:
  sessionAffinity: ClientIP
```

(For finer control, use an Ingress that supports sticky sessions.)

### 2. OIDC login needs a shared store

If you use `--auth-mode oidc`, the login handshake spans several requests. With
multiple copies you must give them a **shared** session store so any copy can
finish a login another copy started. See the "Session storage" part of
[configuration.md](configuration.md).

Short version:

```bash
feast-mcp \
  --feast-url http://feature-server:6566 \
  --auth-mode oidc \
  --oidc-discovery-url https://keycloak.example.com/realms/feast/.well-known/openid-configuration \
  --oidc-client-id feast-mcp \
  --session-storage-backend redis \
  --transport http --port 8000
```

with Redis connection details in `feast_mcp.yaml` under `session_storage.options`.

## Send logs to your monitoring system

To ship logs to an OpenTelemetry collector, install the extra and set an
endpoint. See [configuration.md](configuration.md) for all the options.

```bash
pip install 'feast-mcp[otel]'

feast-mcp \
  --feast-url http://feature-server:6566 \
  --transport http --port 8000 \
  --otel-endpoint http://otel-collector:4317 \
  --log-format json
```

## Quick checklist for production

- [ ] Use `--transport http`.
- [ ] Put it behind HTTPS (a reverse proxy or ingress).
- [ ] Turn on session affinity if you run more than one copy.
- [ ] If using OIDC with more than one copy, configure shared session storage.
- [ ] Set `--log-format json` and an OTEL endpoint for monitoring.
- [ ] Set liveness/readiness probes.
