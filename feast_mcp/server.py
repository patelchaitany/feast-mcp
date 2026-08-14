"""Feast MCP server built on FastMCP.

Composes two sub-servers behind a single MCP endpoint:

- **features** — proxies to the Feast feature server (online features,
  vector search, push, materialization).  Mounted when ``--feast-url``
  or ``features.url`` in config is provided.
- **registry** — proxies to the Feast REST registry server (browse
  feature views, entities, data sources, lineage).  Mounted when
  ``--registry-url`` or ``registry.url`` in config is provided.

Configuration is loaded from (highest priority first):
  1. CLI arguments
  2. Environment variables
  3. ``feast_mcp.yaml`` config file (or ``--config path``)
"""

import argparse
import logging

from dotenv import load_dotenv

from fastmcp import FastMCP

from feast_mcp.auth import create_oidc_auth
from feast_mcp.client import FeastClient
from feast_mcp.config import Config, load_config

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "feast",
    instructions=(
        "Feast Feature Store — retrieve online features, search documents, "
        "manage materialization, and browse the feature registry."
    ),
)


def _mount_servers(cfg: Config) -> None:
    if cfg.features.url:
        from feast_mcp.features import create_features_mcp

        client = FeastClient(cfg.features.url, timeout=cfg.timeout)
        mcp.mount(create_features_mcp(client), namespace="features")
        logger.info("Feature tools mounted from %s", cfg.features.url)

    if cfg.registry.url:
        from feast_mcp.registry import create_registry_mcp

        client = FeastClient(cfg.registry.url, timeout=cfg.timeout)
        mcp.mount(create_registry_mcp(client), namespace="registry")
        logger.info("Registry tools mounted from %s", cfg.registry.url)


def _configure_auth(cfg: Config) -> None:
    if cfg.auth.mode != "oidc":
        return

    base_url = cfg.auth.base_url or f"http://localhost:{cfg.server.port}"
    mcp.auth = create_oidc_auth(
        discovery_url=cfg.auth.discovery_url,
        client_id=cfg.auth.client_id,
        client_secret=cfg.auth.client_secret,
        base_url=base_url,
        audience=cfg.auth.audience,
    )


def _build_http_app(cfg: Config):
    if cfg.server.transport == "sse":
        kwargs = {"path": "/sse", "transport": "sse"}
    else:
        kwargs = {"path": "/mcp", "transport": cfg.server.transport}
    return mcp.http_app(**kwargs)


def _run_uvicorn(cfg: Config) -> None:
    import uvicorn

    app = _build_http_app(cfg)
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port)


def _run_gunicorn(cfg: Config) -> None:
    from gunicorn.app.base import BaseApplication

    asgi_app = _build_http_app(cfg)

    class FeastMCPApplication(BaseApplication):
        def load_config(self) -> None:
            self.cfg.set("bind", f"{cfg.server.host}:{cfg.server.port}")
            self.cfg.set("workers", cfg.server.workers)
            self.cfg.set("worker_class", "uvicorn.workers.UvicornWorker")
            self.cfg.set("accesslog", "-")

        def load(self):
            return asgi_app

    FeastMCPApplication().run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Feast MCP Server")
    parser.add_argument(
        "--config", default=None,
        help="Path to feast_mcp.yaml config file",
    )
    parser.add_argument("--feast-url", default=None)
    parser.add_argument("--registry-url", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http", "sse"],
        default=None,
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)

    auth_group = parser.add_argument_group("authentication")
    auth_group.add_argument(
        "--auth-mode", choices=["passthrough", "oidc"], default=None,
    )
    auth_group.add_argument("--oidc-discovery-url", default=None)
    auth_group.add_argument("--oidc-client-id", default=None)
    auth_group.add_argument("--oidc-client-secret", default=None)
    auth_group.add_argument("--oidc-audience", default=None)
    auth_group.add_argument("--base-url", default=None)

    args = parser.parse_args()

    cli_args = {k: v for k, v in vars(args).items() if v is not None and k != "config"}
    cfg = load_config(config_path=args.config, cli_args=cli_args)

    # --- Validate ---
    if not cfg.features.url and not cfg.registry.url:
        parser.error(
            "At least one of --feast-url or --registry-url must be provided "
            "(via CLI, env var, or feast_mcp.yaml)"
        )

    if cfg.auth.mode == "oidc" and not all([cfg.auth.discovery_url, cfg.auth.client_id]):
        parser.error(
            "--oidc-discovery-url and --oidc-client-id are required with --auth-mode oidc"
        )

    if cfg.server.transport == "sse" and cfg.server.workers and cfg.server.workers > 1:
        parser.error(
            "SSE transport does not support multiple workers. "
            "Use --transport http for multi-worker scaling, "
            "or remove --workers for single-process SSE"
        )

    # --- Setup ---
    _mount_servers(cfg)
    _configure_auth(cfg)

    # --- Run ---
    if cfg.server.transport == "stdio":
        mcp.run(transport="stdio")
    elif cfg.server.workers:
        _run_gunicorn(cfg)
    else:
        _run_uvicorn(cfg)


if __name__ == "__main__":
    main()
