"""Feast MCP server built on FastMCP.

Composes two sub-servers behind a single MCP endpoint:

- **features** — proxies to the Feast feature server (online features,
  vector search, push, materialization).  Always mounted.
- **registry** — proxies to the Feast REST registry server (browse
  feature views, entities, data sources, lineage).  Mounted only when
  ``--registry-url`` is provided.

The caller's bearer token (OIDC or Kubernetes SA token) is passed
through so that upstream servers perform their own auth/RBAC checks.
"""

import argparse
import logging
import os

from dotenv import load_dotenv

from fastmcp import FastMCP

from feast_mcp.auth import create_oidc_auth
from feast_mcp.client import FeastClient

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "feast",
    instructions=(
        "Feast Feature Store — retrieve online features, search documents, "
        "manage materialization, and browse the feature registry."
    ),
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    parser = argparse.ArgumentParser(description="Feast MCP Server")
    parser.add_argument(
        "--feast-url",
        default=os.environ.get("FEAST_MCP_FEATURE_SERVER_URL"),
        help="Base URL of the Feast feature server. When provided, "
        "feature tools are mounted under the 'features_' prefix "
        "(env: FEAST_MCP_FEATURE_SERVER_URL)",
    )
    parser.add_argument(
        "--registry-url",
        default=os.environ.get("FEAST_MCP_REGISTRY_URL"),
        help="Base URL of the Feast REST registry server. When provided, "
        "registry tools are mounted under the 'registry_' prefix "
        "(env: FEAST_MCP_REGISTRY_URL)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for network transports (default: 8000)",
    )

    auth_group = parser.add_argument_group("authentication")
    auth_group.add_argument(
        "--auth-mode",
        choices=["passthrough", "oidc"],
        default=os.environ.get("FEAST_MCP_AUTH_MODE", "passthrough"),
        help="Auth mode: passthrough accepts any token, oidc enables browser login "
        "(env: FEAST_MCP_AUTH_MODE, default: passthrough)",
    )
    auth_group.add_argument(
        "--oidc-discovery-url",
        default=os.environ.get("FEAST_MCP_OIDC_DISCOVERY_URL"),
        help="OIDC discovery URL — same value as auth.auth_discovery_url in "
        "feature_store.yaml, e.g. https://keycloak.example.com/realms/feast/"
        ".well-known/openid-configuration "
        "(env: FEAST_MCP_OIDC_DISCOVERY_URL)",
    )
    auth_group.add_argument(
        "--oidc-client-id",
        default=os.environ.get("FEAST_MCP_OIDC_CLIENT_ID"),
        help="OAuth client ID registered with the OIDC provider "
        "(env: FEAST_MCP_OIDC_CLIENT_ID)",
    )
    auth_group.add_argument(
        "--oidc-client-secret",
        default=os.environ.get("FEAST_MCP_OIDC_CLIENT_SECRET"),
        help="OAuth client secret — omit for public clients using PKCE "
        "(env: FEAST_MCP_OIDC_CLIENT_SECRET)",
    )
    auth_group.add_argument(
        "--oidc-audience",
        default=os.environ.get("FEAST_MCP_OIDC_AUDIENCE"),
        help="Expected JWT audience claim "
        "(env: FEAST_MCP_OIDC_AUDIENCE)",
    )
    auth_group.add_argument(
        "--base-url",
        default=os.environ.get("FEAST_MCP_BASE_URL"),
        help="Public base URL of this MCP server for OAuth callbacks, "
        "e.g. https://mcp.example.com:8000 "
        "(env: FEAST_MCP_BASE_URL, default: http://localhost:<port>)",
    )

    args = parser.parse_args()

    if not args.feast_url and not args.registry_url:
        parser.error(
            "At least one of --feast-url or --registry-url must be provided "
            "(or set FEAST_MCP_FEATURE_SERVER_URL / FEAST_MCP_REGISTRY_URL)"
        )

    # --- Mount feature server tools ---
    if args.feast_url:
        from feast_mcp.features import create_features_mcp

        features_client = FeastClient(args.feast_url, timeout=args.timeout)
        features_mcp = create_features_mcp(features_client)
        mcp.mount(features_mcp, namespace="features")
        logger.info("Feature tools mounted from %s", args.feast_url)

    # --- Mount registry tools ---
    if args.registry_url:
        from feast_mcp.registry import create_registry_mcp

        registry_client = FeastClient(args.registry_url, timeout=args.timeout)
        registry_mcp = create_registry_mcp(registry_client)
        mcp.mount(registry_mcp, namespace="registry")
        logger.info("Registry tools mounted from %s", args.registry_url)

    # --- Auth ---
    if args.auth_mode == "oidc":
        if not all([args.oidc_discovery_url, args.oidc_client_id]):
            parser.error(
                "--oidc-discovery-url and --oidc-client-id are required with --auth-mode oidc "
                "(or set FEAST_MCP_OIDC_DISCOVERY_URL and FEAST_MCP_OIDC_CLIENT_ID)"
            )

        base_url = args.base_url or f"http://localhost:{args.port}"
        mcp.auth = create_oidc_auth(
            discovery_url=args.oidc_discovery_url,
            client_id=args.oidc_client_id,
            client_secret=args.oidc_client_secret,
            base_url=base_url,
            audience=args.oidc_audience,
        )

    run_kwargs = {"transport": args.transport}
    if args.transport not in ("stdio",):
        run_kwargs["port"] = args.port
    mcp.run(**run_kwargs)


if __name__ == "__main__":
    main()
