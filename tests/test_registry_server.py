"""Registry server MCP migration tests."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from helpers import (
    call_mcp_tool_sync,
    call_rest,
    extract_path_and_query_params,
    normalize_response,
)
from manifest import (
    REGISTRY_TOOLS,
    HttpMethod,
    ToolTestSpec,
)


@pytest.mark.parametrize(
    "spec",
    REGISTRY_TOOLS,
    ids=lambda s: s.tool_name,
)
def test_registry_tool(
    spec: ToolTestSpec, registry_server: str, mcp_server: str
) -> None:
    """Test a registry tool: REST baseline + MCP comparison if migrated."""
    for sample_input in spec.sample_inputs:
        resolved_endpoint: str
        body_params: dict[str, Any]
        query_params: dict[str, str]
        resolved_endpoint, body_params, query_params = extract_path_and_query_params(
            spec.feast_endpoint, sample_input
        )

        # 1. Call REST endpoint directly
        rest_response: httpx.Response = call_rest(
            base_url=registry_server,
            endpoint=resolved_endpoint,
            method=spec.http_method,
            payload=body_params if spec.http_method == HttpMethod.POST else None,
            query_params=query_params if spec.http_method != HttpMethod.POST else None,
        )
        # Registry endpoints may return 404 for objects that don't exist yet
        # That's OK for baseline — we just need the endpoint to be reachable
        assert rest_response.status_code in (200, 201, 202, 404, 422), (
            f"REST {spec.http_method.value} {resolved_endpoint} returned "
            f"{rest_response.status_code}: {rest_response.text}"
        )

        if not spec.migrated:
            continue

        # 2. Call MCP tool on the standalone MCP server
        mcp_result: Any = call_mcp_tool_sync(
            mcp_url=f"{mcp_server}/sse",
            tool_name=spec.tool_name,
            args=sample_input,
        )

        # 3. Compare
        if spec.mutation:
            assert not getattr(mcp_result, "isError", False), (
                f"MCP tool {spec.tool_name} returned error: {mcp_result}"
            )
            if spec.verify_endpoint:
                verify_response: httpx.Response = call_rest(
                    base_url=registry_server,
                    endpoint=spec.verify_endpoint,
                    method=HttpMethod.GET,
                )
                assert verify_response.status_code == 200
        else:
            rest_data: Any = normalize_response(rest_response.json())
            mcp_content: Any = mcp_result
            if hasattr(mcp_result, "content"):
                text_parts: list[str] = [
                    part.text for part in mcp_result.content if hasattr(part, "text")
                ]
                raw_text: str = "".join(text_parts)
                try:
                    mcp_content = json.loads(raw_text)
                except json.JSONDecodeError:
                    mcp_content = raw_text
            mcp_data: Any = normalize_response(mcp_content)
            assert rest_data == mcp_data, (
                f"Response mismatch for {spec.tool_name}:\n"
                f"REST: {rest_data}\n"
                f"MCP:  {mcp_data}"
            )
