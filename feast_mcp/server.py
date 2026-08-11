"""Feast MCP server built on FastMCP.

Acts as a proxy — every tool call is forwarded to the upstream Feast
feature server over HTTP.  The caller's bearer token (OIDC or
Kubernetes SA token) is passed through so that the feature server
performs its own auth/RBAC checks.
"""

import argparse
import logging
import os
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

from fastmcp import FastMCP

from feast_mcp.auth import (
    create_oidc_auth,
    get_auth_token,
)
from feast_mcp.client import FeastClient

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "feast-feature-store",
    instructions="Feast Feature Store — retrieve online features, search documents, manage materialization",
)

_client: Optional[FeastClient] = None


def _get_client() -> FeastClient:
    if _client is None:
        raise RuntimeError(
            "FeastClient not initialised. "
            "Call configure() or pass --feast-url before starting the server."
        )
    return _client


def configure(feast_url: str, timeout: float = 30.0) -> None:
    global _client
    _client = FeastClient(feast_url, timeout=timeout)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
async def get_online_features(
    features: List[str],
    entities: Dict[str, List[Any]],
    feature_service: Optional[str] = None,
    full_feature_names: bool = False,
) -> Any:
    """Retrieve online feature values for a set of entities.

    Args:
        features: Feature references in 'feature_view:feature' format.
        entities: Entity key-value map — each key maps to a list of values.
        feature_service: Optional feature service name (used instead of features list).
        full_feature_names: If true, response keys include the feature view name.
    """
    body: Dict[str, Any] = {
        "features": features,
        "entities": entities,
        "full_feature_names": full_feature_names,
    }
    if feature_service is not None:
        body["feature_service"] = feature_service
    return await _get_client().request(
        "POST", "/get-online-features", token=get_auth_token(), json=body
    )


@mcp.tool
async def search(
    features: List[str],
    top_k: int = 5,
    query: Optional[List[float]] = None,
    query_string: Optional[str] = None,
    feature_service: Optional[str] = None,
    distance_metric: Optional[str] = None,
    full_feature_names: bool = False,
    api_version: int = 2,
) -> Any:
    """Vector similarity search against online document embeddings.

    Args:
        features: Feature references to retrieve.
        top_k: Number of nearest results to return.
        query: Query embedding vector (list of floats).
        query_string: Text query (used when the server handles embedding).
        feature_service: Optional feature service name.
        distance_metric: Optional distance metric override.
        full_feature_names: If true, response keys include the feature view name.
        api_version: API version for the search endpoint.
    """
    body: Dict[str, Any] = {
        "features": features,
        "top_k": top_k,
        "full_feature_names": full_feature_names,
        "api_version": api_version,
    }
    if query is not None:
        body["query"] = query
    if query_string is not None:
        body["query_string"] = query_string
    if feature_service is not None:
        body["feature_service"] = feature_service
    if distance_metric is not None:
        body["distance_metric"] = distance_metric
    return await _get_client().request(
        "POST", "/search", token=get_auth_token(), json=body
    )


@mcp.tool
async def list_vector_stores() -> Any:
    """List all available vector stores."""
    return await _get_client().request(
        "GET", "/v1/vector_stores", token=get_auth_token()
    )


@mcp.tool
async def get_vector_store(vector_store_id: str) -> Any:
    """Get details of a specific vector store.

    Args:
        vector_store_id: Identifier of the vector store.
    """
    return await _get_client().request(
        "GET",
        f"/v1/vector_stores/{vector_store_id}",
        token=get_auth_token(),
    )


@mcp.tool
async def vector_store_search(
    vector_store_id: str,
    query: Union[str, List[str]],
    max_num_results: int = 10,
) -> Any:
    """OpenAI-compatible vector store search.

    Args:
        vector_store_id: Identifier of the vector store to search.
        query: Text query or list of text queries.
        max_num_results: Maximum number of results to return.
    """
    body: Dict[str, Any] = {
        "query": query,
        "max_num_results": max_num_results,
    }
    return await _get_client().request(
        "POST",
        f"/v1/vector_stores/{vector_store_id}/search",
        token=get_auth_token(),
        json=body,
    )


@mcp.tool
async def push(
    push_source_name: str,
    df: Dict[str, Any],
    to: str = "online",
    allow_registry_cache: bool = True,
    transform_on_write: bool = True,
) -> str:
    """Push features into the online or offline store.

    Args:
        push_source_name: Name of the push source defined in the feature repo.
        df: Column-oriented dict representing the DataFrame to push.
        to: Target store — 'online', 'offline', or 'online_and_offline'.
        allow_registry_cache: Allow using the cached registry.
        transform_on_write: Apply on-demand transforms before writing.
    """
    body: Dict[str, Any] = {
        "push_source_name": push_source_name,
        "df": df,
        "to": to,
        "allow_registry_cache": allow_registry_cache,
        "transform_on_write": transform_on_write,
    }
    await _get_client().request(
        "POST", "/push", token=get_auth_token(), json=body
    )
    return "ok"


@mcp.tool
async def materialize(
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
    feature_views: Optional[List[str]] = None,
) -> str:
    """Materialize features from the offline store to the online store.

    Args:
        start_ts: Start timestamp (ISO-8601).
        end_ts: End timestamp (ISO-8601).
        feature_views: Specific feature views to materialize (all if omitted).
    """
    body: Dict[str, Any] = {}
    if start_ts is not None:
        body["start_ts"] = start_ts
    if end_ts is not None:
        body["end_ts"] = end_ts
    if feature_views is not None:
        body["feature_views"] = feature_views
    await _get_client().request(
        "POST", "/materialize", token=get_auth_token(), json=body
    )
    return "ok"


@mcp.tool
async def materialize_incremental(
    end_ts: str,
    feature_views: Optional[List[str]] = None,
) -> str:
    """Run incremental materialization up to the given timestamp.

    Args:
        end_ts: End timestamp (ISO-8601).
        feature_views: Specific feature views to materialize (all if omitted).
    """
    body: Dict[str, Any] = {"end_ts": end_ts}
    if feature_views is not None:
        body["feature_views"] = feature_views
    await _get_client().request(
        "POST", "/materialize-incremental", token=get_auth_token(), json=body
    )
    return "ok"


@mcp.tool
async def health() -> Any:
    """Check the health of the Feast feature server."""
    return await _get_client().request("GET", "/health", token=get_auth_token())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    parser = argparse.ArgumentParser(description="Feast MCP Server")
    parser.add_argument(
        "--feast-url",
        default="http://localhost:6566",
        help="Base URL of the Feast feature server (default: http://localhost:6566)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
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

    configure(args.feast_url, timeout=args.timeout)

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
    else:
        pass  # No auth — allow unauthenticated connections

    mcp.run(transport=args.transport, port=args.port)


if __name__ == "__main__":
    main()
