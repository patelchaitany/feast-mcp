# Feast MCP Server — Documentation

The Feast MCP server is a small standalone service. It sits in front of your
Feast servers and lets an AI client (Cursor, VS Code, Claude, etc.) talk to
Feast through the Model Context Protocol (MCP).

It does not store features itself. It forwards each tool call to your running
Feast servers over HTTP:

- **features** — the Feast feature server (online features, vector search, push,
  materialization).
- **registry** — the Feast REST registry server (browse projects, entities,
  feature views, and so on).

## Guides

| Guide | Read this when you want to… |
|---|---|
| [Configuration](configuration.md) | Set URLs, choose a transport, turn on auth, logging, and OTEL |
| [Deployment](deployment.md) | Run it for real — locally, with Docker, or on Kubernetes |
| [Development](development.md) | Change the code, run the tests, add a new tool |

## The 30-second version

```bash
# Install
cd MCP
pip install -e .

# Point it at your Feast servers and run it
feast-mcp \
  --feast-url http://localhost:6566 \
  --registry-url http://localhost:8080
```

That starts the server in **stdio** mode, which is what IDE clients use. To run
it as a network service instead, add `--transport http --port 8000` and give
clients the URL `http://localhost:8000/mcp`.

See [Configuration](configuration.md) for everything you can change, and
[Deployment](deployment.md) for how to run it in production.
