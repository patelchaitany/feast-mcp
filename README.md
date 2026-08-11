# Feast MCP Server

Standalone MCP server for Feast, built on the [MCP SDK](https://github.com/modelcontextprotocol/python-sdk).

Currently operates as a **proxy** — it forwards every tool call to an upstream Feast feature server over HTTP, passing through the caller's `Authorization: Bearer <token>` header so that the feature server handles OIDC / Kubernetes RBAC as usual.

## Quick start

```bash
cd MCP
pip install -e .

# stdio (default) — point at your running Feast feature server
feast-mcp --feast-url http://localhost:6566

# SSE transport on a custom port
feast-mcp --feast-url http://localhost:6566 --transport sse --port 8000
```

## Tools exposed

| Tool | Upstream endpoint | Description |
|---|---|---|
| `get_online_features` | `POST /get-online-features` | Retrieve online feature values |
| `search` | `POST /search` | Vector similarity search |
| `list_vector_stores` | `GET /v1/vector_stores` | List vector stores |
| `get_vector_store` | `GET /v1/vector_stores/{id}` | Get a vector store |
| `vector_store_search` | `POST /v1/vector_stores/{id}/search` | OpenAI-compatible vector search |
| `push` | `POST /push` | Push features to the store |
| `materialize` | `POST /materialize` | Materialize features |
| `materialize_incremental` | `POST /materialize-incremental` | Incremental materialization |
| `health` | `GET /health` | Health check |

## Authorization

The MCP server itself does **not** validate tokens. It forwards the bearer token from the MCP request context to the upstream feature server, which performs OIDC or Kubernetes token validation and RBAC enforcement.

## IDE / client configuration

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
