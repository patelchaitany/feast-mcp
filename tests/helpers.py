"""Helper functions for MCP migration tests.

Utility functions for calling REST endpoints, MCP tools, normalizing
responses, and discovering OpenAPI endpoints.  Imported by test files
and conftest.py — NOT a pytest plugin or fixture file.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from manifest import (
    DiscoveredEndpoint,
    HttpMethod,
    ServerType,
)

# ---------------------------------------------------------------------------
# Path parameter regex
# ---------------------------------------------------------------------------

_PATH_PARAM_RE: re.Pattern[str] = re.compile(r"\{(\w+)\}")


# ---------------------------------------------------------------------------
# extract_path_and_query_params
# ---------------------------------------------------------------------------


def extract_path_and_query_params(
    endpoint: str,
    sample_input: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, str]]:
    """Given an endpoint template and sample input, split into path, body, and query parts.

    Returns:
        (resolved_endpoint, body_params, query_params)
    """
    path_param_names: list[str] = _PATH_PARAM_RE.findall(endpoint)

    resolved_endpoint: str = endpoint
    remaining: dict[str, Any] = dict(sample_input)

    for param_name in path_param_names:
        if param_name in remaining:
            value: str = str(remaining.pop(param_name))
            resolved_endpoint = resolved_endpoint.replace(f"{{{param_name}}}", value)

    query_params: dict[str, str] = {k: str(v) for k, v in remaining.items()}
    body_params: dict[str, Any] = dict(remaining)

    return resolved_endpoint, body_params, query_params


# ---------------------------------------------------------------------------
# call_rest
# ---------------------------------------------------------------------------


def call_rest(
    base_url: str,
    endpoint: str,
    method: HttpMethod,
    payload: dict[str, Any] | None = None,
    query_params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
) -> httpx.Response:
    """Call a REST endpoint directly via httpx."""
    resolved_endpoint: str = endpoint

    if path_params:
        for param_name, param_value in path_params.items():
            resolved_endpoint = resolved_endpoint.replace(
                f"{{{param_name}}}", param_value
            )

    url: str = base_url + resolved_endpoint
    request_headers: dict[str, str] = headers or {}

    with httpx.Client(timeout=30.0) as client:
        if method in (HttpMethod.GET, HttpMethod.DELETE):
            merged_params: dict[str, str] = dict(query_params or {})
            if payload:
                for k, v in payload.items():
                    merged_params[k] = str(v)
            response: httpx.Response = client.request(
                method.value,
                url,
                params=merged_params if merged_params else None,
                headers=request_headers,
            )
        else:
            response = client.request(
                method.value,
                url,
                json=payload,
                params=query_params if query_params else None,
                headers=request_headers,
            )

    return response


# ---------------------------------------------------------------------------
# call_mcp_tool (async + sync wrapper)
# ---------------------------------------------------------------------------


async def call_mcp_tool(
    mcp_url: str,
    tool_name: str,
    args: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> Any:
    """Call an MCP tool via the mcp Python SDK ClientSession."""
    import httpx as _httpx

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    http_client: _httpx.AsyncClient | None = None
    if headers:
        http_client = _httpx.AsyncClient(headers=headers)

    async with streamable_http_client(
        mcp_url, http_client=http_client
    ) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result: Any = await session.call_tool(tool_name, args)
            return result


def call_mcp_tool_sync(
    mcp_url: str,
    tool_name: str,
    args: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> Any:
    """Synchronous wrapper around call_mcp_tool."""
    result: Any = asyncio.run(call_mcp_tool(mcp_url, tool_name, args, headers))
    return result


# ---------------------------------------------------------------------------
# normalize_response
# ---------------------------------------------------------------------------


def normalize_response(data: Any) -> Any:
    """Sort dict keys recursively for deterministic comparison."""
    if isinstance(data, dict):
        sorted_dict: dict[str, Any] = {
            k: normalize_response(v) for k, v in sorted(data.items())
        }
        return sorted_dict
    elif isinstance(data, list):
        normalized_list: list[Any] = [normalize_response(item) for item in data]
        return normalized_list
    else:
        return data


# ---------------------------------------------------------------------------
# auto_discover_endpoints
# ---------------------------------------------------------------------------


def auto_discover_endpoints(
    openapi_url: str,
    server_type: ServerType,
) -> list[DiscoveredEndpoint]:
    """Fetch OpenAPI schema and parse into DiscoveredEndpoint list."""
    with httpx.Client(timeout=30.0) as client:
        response: httpx.Response = client.get(openapi_url)
        response.raise_for_status()

    schema: dict[str, Any] = response.json()
    endpoints: list[DiscoveredEndpoint] = []

    paths: dict[str, Any] = schema.get("paths", {})
    for path, path_item in paths.items():
        http_methods: list[str] = ["get", "post", "delete", "put", "patch"]
        for http_method in http_methods:
            operation: dict[str, Any] | None = path_item.get(http_method)
            if operation is None:
                continue

            request_schema: dict[str, Any] = {}
            request_body: dict[str, Any] | None = operation.get("requestBody")
            if request_body:
                content: dict[str, Any] = request_body.get("content", {})
                json_content: dict[str, Any] | None = content.get("application/json")
                if json_content:
                    request_schema = json_content.get("schema", {})

            response_schema: dict[str, Any] = {}
            responses: dict[str, Any] = operation.get("responses", {})
            success_response: dict[str, Any] | None = responses.get(
                "200"
            ) or responses.get("201")
            if success_response:
                resp_content: dict[str, Any] = success_response.get("content", {})
                resp_json: dict[str, Any] | None = resp_content.get("application/json")
                if resp_json:
                    response_schema = resp_json.get("schema", {})

            parameters: list[dict[str, Any]] = operation.get("parameters", [])

            endpoint: DiscoveredEndpoint = DiscoveredEndpoint(
                path=path,
                method=http_method.upper(),
                server_type=server_type,
                request_schema=request_schema,
                response_schema=response_schema,
                parameters=parameters,
            )
            endpoints.append(endpoint)

    return endpoints


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------


def get_token(
    oidc_url: str,
    username: str,
    password: str = "password",
) -> str:
    """Get an access token from the mock OIDC server."""
    with httpx.Client(timeout=10.0) as client:
        response: httpx.Response = client.post(
            f"{oidc_url}/token",
            content=f"grant_type=password&username={username}&password={password}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data: dict[str, Any] = response.json()
        access_token: str = token_data["access_token"]
        return access_token
