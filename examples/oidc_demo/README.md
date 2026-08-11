# Feast MCP Server — OIDC Demo

End-to-end example of the standalone `feast-mcp` server with OIDC authentication, configured entirely via a `.env` file.

## Architecture

```
Demo Client                    feast-mcp server              Feast feature server
(MCP SDK)  ──── MCP/SSE ────>  (reads .env for OIDC)  ──>   (validates tokens, RBAC)
                                      │
                                      │ OIDC discovery + JWKS
                                      ▼
                               Mock OIDC server
```

The `.env` file configures OIDC without any CLI flags:

```env
FEAST_MCP_AUTH_MODE=oidc
FEAST_MCP_OIDC_DISCOVERY_URL=http://127.0.0.1:8081/.well-known/openid-configuration
FEAST_MCP_OIDC_CLIENT_ID=feast-demo
FEAST_MCP_BASE_URL=http://localhost:8000
```

## Quick start

```bash
cd MCP/examples/oidc_demo
./run_demo.sh
```

This starts three processes (mock OIDC, Feast feature server, feast-mcp), applies sample data, and runs the demo client.

## Manual setup

```bash
# 1. Start mock OIDC server
python mock_oidc_server.py

# 2. Generate data and apply registry
python setup_data.py

# 3. Start Feast feature server
cd feature_repo && feast serve --host 0.0.0.0 --port 6566 &

# 4. Start feast-mcp (picks up OIDC config from .env)
cd ..
feast-mcp --feast-url http://localhost:6566 --transport sse --port 8000

# 5. In another terminal, run the demo client
python demo_client.py --username admin
python demo_client.py --username reader
python demo_client.py --username user
```

## Test users

| Username | Password | Roles     | Expected access               |
|----------|----------|-----------|-------------------------------|
| admin    | admin    | `[admin]` | Full read/write/manage        |
| reader   | reader   | `[reader]`| Read-only (describe + read)   |
| user     | user     | `[user]`  | Denied (no feature permissions)|

## IDE configuration

Point your IDE at the MCP server (not the Feast server):

```json
{
  "mcpServers": {
    "feast": {
      "command": "feast-mcp",
      "args": ["--feast-url", "http://localhost:6566", "--transport", "sse", "--port", "8000"]
    }
  }
}
```

The `.env` file must be in the working directory (or a parent) so `feast-mcp` picks it up at startup.
