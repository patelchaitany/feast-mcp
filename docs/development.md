# Development

This page is for people who want to change the code, run the tests, or add a new
tool.

## Set up your environment

The project uses [uv](https://docs.astral.sh/uv/) to manage dependencies.

```bash
cd MCP

# Install everything, including dev and test tools
make install-dev
# (this runs: uv sync)
```

If you prefer plain pip:

```bash
pip install -e '.[dev]'
```

## How the code is laid out

```
feast_mcp/
  server.py          Puts everything together and is the CLI entry point.
  features.py        The 9 feature-server tools.
  registry.py        The 13 registry tools (read-only).
  client.py          A small HTTP client that calls the Feast servers.
  auth.py            Auth helpers (passthrough and OIDC).
  config.py          Reads settings from flags, env vars, and YAML.
  session_storage/   Builds the shared store used for OIDC login state.
  observability/     Sets up console + OpenTelemetry logging, plus a span
                     per request so logs share a trace id.
```

The big idea: **the MCP server owns no data.** Each tool takes some arguments,
calls a Feast HTTP endpoint through `client.py`, and returns the result. If you
understand one tool, you understand them all.

## Run it while developing

Point it at Feast servers you already have running:

```bash
feast-mcp \
  --feast-url http://localhost:6566 \
  --registry-url http://localhost:8080 \
  --transport http --port 8000
```

Turn on debug logs to see more:

```bash
feast-mcp --feast-url http://localhost:6566 --log-level DEBUG
```

## Run the tests

The test suite starts real Feast servers in the background and checks that each
tool returns the same thing as the underlying REST call.

```bash
make test                  # everything
make test-feature-server   # just the feature-server tools
make test-registry         # just the registry tools
make test-auth             # just the auth tests
make test-no-auth          # everything except auth
```

If you already have servers running and don't want the tests to start their own,
set the URLs first (this also skips the slow apply/materialize step):

```bash
export FEAST_FEATURE_SERVER_URL=http://localhost:6566
export FEAST_REGISTRY_SERVER_URL=http://localhost:8080/api/v1
export FEAST_MCP_SERVER_URL=http://localhost:8000
make test-feature-server
```

See `tests/README.md` for the full list of test options.

## Check style and types

```bash
make lint      # ruff check feast_mcp/ tests/
make format    # ruff format + ruff check --fix
```

Run these before you open a pull request. To check a single file quickly:

```bash
uv run ruff check feast_mcp/path/to/file.py
uv run ruff format feast_mcp/path/to/file.py
```

## Add a new tool

Say Feast adds a new endpoint and you want to expose it.

1. **Pick the right file.** Feature-server endpoints go in `features.py`;
   registry endpoints go in `registry.py`.

2. **Write the tool.** Add an `async def` inside the `create_*_mcp` function and
   mark it with the `@..._mcp.tool` decorator. Use the existing tools as a
   template. The pattern is always the same:

   ```python
   @features_mcp.tool
   async def my_new_tool(some_arg: str) -> Any:
       """A short sentence explaining what this does.

       Args:
           some_arg: What this argument is for.
       """
       return await client.request(
           "POST", "/my-new-endpoint", token=get_auth_token(), json={"some_arg": some_arg}
       )
   ```

   Two things matter for the AI client:
   - **Type hints** on every argument — they become the tool's input schema.
   - **A clear docstring** — the model reads it to decide when to use the tool.

3. **Pass the auth token.** Always include `token=get_auth_token()` so the
   caller's login is forwarded to Feast.

4. **Add a test.** In `tests/manifest.py`, add a `ToolTestSpec` for the new tool
   with a realistic sample input, and set `migrated=True`. Then run
   `make test`.

5. **Update the README** table of tools.

## Add a new setting

1. Add the field to the right dataclass in `config.py` (or
   `observability/config.py` for logging).
2. Read it from flags, env vars, and YAML in the matching `load_*` function,
   keeping the order **flag → env → YAML → default**.
3. Use it where it's needed in `server.py`.
4. Add a CLI flag in `server.py`'s `main()` if it should be settable that way.
5. Document it in `docs/configuration.md` and `feast_mcp.yaml.example`.

## Optional features and their extra packages

Some features need extra packages so the base install stays small:

| Feature | Install |
|---|---|
| YAML config file | `pip install 'feast-mcp[yaml]'` |
| Multi-worker serving | `pip install 'feast-mcp[server]'` |
| OpenTelemetry logs + traces | `pip install 'feast-mcp[otel]'` |
| A session-storage backend | `pip install 'py-key-value-aio[redis]'` (or `valkey`, `postgresql`, …) |

The code is written so that if one of these packages is missing, the server
either turns that feature off with a clear warning or tells you exactly what to
install — it does not crash.

## Before you open a pull request

- [ ] `make format`
- [ ] `make lint`
- [ ] `make test`
- [ ] Update the docs if you changed behavior.
- [ ] Use a conventional commit title, e.g. `feat: Add my new tool`.
