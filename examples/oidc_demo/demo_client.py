"""
Demo client for the Feast MCP server with OIDC auth.

Acquires a token from the mock OIDC server, then connects to the
feast-mcp server (not the Feast feature server directly) and calls
tools as different roles to demonstrate RBAC enforcement.

Prerequisites:
  1. Mock OIDC server running:  python mock_oidc_server.py
  2. Data applied:              python setup_data.py
  3. Feast feature server:      cd feature_repo && feast serve --port 6566
  4. Feast MCP server:          feast-mcp  (reads .env for OIDC config)

Usage:
    python demo_client.py                  # interactive role selection
    python demo_client.py --username admin
    python demo_client.py --username user
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx

OIDC_SERVER = os.getenv("OIDC_SERVER_URL", "http://127.0.0.1:8081")
MCP_SERVER = os.getenv("FEAST_MCP_URL", "http://localhost:8000")

TOOL_CALLS: list[dict[str, Any]] = [
    {
        "name": "Read Online Features",
        "tool": "get_online_features",
        "args": {
            "features": [
                "customer_profile:name",
                "customer_profile:email",
                "customer_profile:plan_tier",
                "customer_profile:account_age_days",
                "customer_profile:total_spend",
            ],
            "entities": {"customer_id": ["C1001"]},
        },
    },
    {
        "name": "Health Check",
        "tool": "health",
        "args": {},
    },
    {
        "name": "List Vector Stores",
        "tool": "list_vector_stores",
        "args": {},
    },
]


def get_token(username: str, password: str) -> str:
    resp = httpx.post(
        f"{OIDC_SERVER}/token",
        content=f"grant_type=password&username={username}&password={password}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        print(f"  ERROR: Failed to get token ({resp.status_code}): {resp.text[:200]}")
        sys.exit(1)
    return resp.json()["access_token"]


def select_role() -> tuple[str, str]:
    print("\n  Choose a role:\n")
    print("  [1] Admin  — full access (read, write, manage)")
    print("  [2] Reader — read-only access")
    print("  [3] User   — no feature permissions (expect denied)")
    while True:
        choice = input("\n  Select [1/2/3]: ").strip()
        if choice == "1":
            return "admin", "admin"
        if choice == "2":
            return "reader", "reader"
        if choice == "3":
            return "user", "user"
        print("  Enter 1, 2, or 3")


async def call_tool_via_mcp(
    session: Any,
    tool_name: str,
    args: dict[str, Any],
) -> tuple[bool, str]:
    try:
        result = await session.call_tool(tool_name, args)
        is_error = getattr(result, "isError", False)
        texts = []
        for content in result.content or []:
            text = getattr(content, "text", None)
            if text:
                texts.append(text)
        response_text = "\n".join(texts) if texts else ""
        return not is_error, response_text
    except Exception as e:
        return False, str(e)


async def run_demo(token: str, username: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    mcp_url = f"{MCP_SERVER}/mcp"

    print(f"\n  Connecting to MCP server at {mcp_url} ...")

    http_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
    )
    async with streamable_http_client(mcp_url, http_client=http_client) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"  Connected | {len(tools)} tools available")

            print(f"\n{'=' * 60}")
            print(f"  RBAC Demo — role: '{username}'")
            print(f"{'=' * 60}")

            results: list[tuple[str, str]] = []

            for scenario in TOOL_CALLS:
                name = scenario["name"]
                tool_name = scenario["tool"]
                args = scenario["args"]

                print(f"\n  > {name} ({tool_name})")

                tool_exists = any(t.name == tool_name for t in tools)
                if not tool_exists:
                    print("    -- Tool not available, skipping")
                    results.append(("SKIP", name))
                    continue

                success, response_text = await call_tool_via_mcp(
                    session, tool_name, args
                )

                if success:
                    print("    ALLOWED")
                    if response_text:
                        try:
                            data = json.loads(response_text)
                            preview = json.dumps(data, default=str)
                            if len(preview) > 120:
                                preview = preview[:117] + "..."
                            print(f"    {preview}")
                        except json.JSONDecodeError:
                            print(f"    {response_text[:120]}")
                    results.append(("ALLOWED", name))
                else:
                    print("    DENIED")
                    if response_text:
                        detail = response_text[:120]
                        print(f"    {detail}")
                    results.append(("DENIED", name))

            print(f"\n{'=' * 60}")
            print(f"  Summary — '{username}'")
            print(f"{'─' * 60}")
            for status, name in results:
                icon = {"ALLOWED": "+", "DENIED": "x", "SKIP": "?"}[status]
                print(f"  [{icon}]  {name:<35} {status}")
            print(f"{'=' * 60}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Feast MCP OIDC demo client")
    parser.add_argument(
        "--username",
        choices=["admin", "reader", "user"],
        help="Role to authenticate as (skips interactive selection)",
    )
    parser.add_argument("--mcp-url", default=None, help="MCP server URL")
    parser.add_argument("--oidc-url", default=None, help="OIDC server URL")
    args = parser.parse_args()

    global MCP_SERVER, OIDC_SERVER
    if args.mcp_url:
        MCP_SERVER = args.mcp_url
    if args.oidc_url:
        OIDC_SERVER = args.oidc_url

    print("=" * 60)
    print("  Feast MCP Server — OIDC Demo")
    print("=" * 60)

    if args.username:
        username, password = args.username, args.username
    else:
        username, password = select_role()

    print(f"\n  Authenticating as '{username}'...")
    token = get_token(username, password)
    print("  Token acquired")

    asyncio.run(run_demo(token, username))


if __name__ == "__main__":
    main()
