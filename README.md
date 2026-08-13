# Feast MCP Server

Standalone MCP server for Feast, built on [FastMCP](https://gofastmcp.com/).

Composes two namespaced sub-servers behind a single MCP endpoint:

- **features** — proxies to the Feast feature server (online features, vector search, push, materialization). Mounted when `--feast-url` is provided.
- **registry** — proxies to the Feast REST registry server (browse feature views, entities, data sources, lineage). Mounted when `--registry-url` is provided.

The caller's `Authorization: Bearer <token>` header is passed through so that upstream servers handle OIDC / Kubernetes RBAC as usual.

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
  server.py      — composition + CLI entry point
  features.py    — feature server tools (9 tools)
  registry.py    — registry server tools (13 tools)
  client.py      — shared HTTP client
  auth.py        — shared auth helpers
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

## IDE / client configuration

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
