"""
Test client for the OTEL demo.

Connects to the running feast-mcp server, lists its tools, and calls a few of
them. Every call flows through the server's get_auth_token(), so this is the
easy way to generate log lines you can then watch in the OpenObserve UI
(http://localhost:5080 -> Logs -> 'default').

Prerequisites (see README.md):
  1. docker compose up -d            # Collector + OpenObserve
  2. python setup_data.py            # sample data + registry
  3. cd feature_repo && feast serve --port 6566
  4. feast-mcp --feast-url http://localhost:6566 --transport http --port 8000 \
       --otel-endpoint http://localhost:4317 --log-format json

Usage:
    python demo_client.py                 # one pass over the sample calls
    python demo_client.py --loop          # keep calling forever (traffic)
    python demo_client.py --loop --interval 2
    python demo_client.py --token <jwt>   # send a bearer token (if server needs one)
    python demo_client.py --mcp-url http://localhost:8000
"""

import argparse
import asyncio
import json
import sys
from typing import Any, Optional

MCP_URL = "http://localhost:8000"

# Sample calls, using the namespaced tool names the server exposes.
TOOL_CALLS: list[dict[str, Any]] = [
    {
        "name": "Health Check",
        "tool": "features_health",
        "args": {},
    },
    {
        "name": "List Vector Stores",
        "tool": "features_list_vector_stores",
        "args": {},
    },
    {
        "name": "Read Online Features",
        "tool": "features_get_online_features",
        "args": {
            "features": [
                "customer_profile:name",
                "customer_profile:email",
                "customer_profile:plan_tier",
                "customer_profile:account_age_days",
                "customer_profile:total_spend",
            ],
            "entities": {"customer_id": ["C1001", "C1002", "C1003"]},
        },
    },
]


async def _call(session: Any, tool: str, args: dict[str, Any]) -> tuple[bool, str]:
    try:
        result = await session.call_tool(tool, args)
        is_error = getattr(result, "isError", False)
        texts = [
            getattr(c, "text", "") for c in (result.content or []) if getattr(c, "text", "")
        ]
        return not is_error, "\n".join(texts)
    except Exception as e:  # noqa: BLE001 - surface any client/transport error
        return False, str(e)


def _preview(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    try:
        text = json.dumps(json.loads(text), default=str)
    except json.JSONDecodeError:
        pass
    return text if len(text) <= limit else text[: limit - 3] + "..."


async def run_once(session: Any, available: set[str]) -> None:
    for scenario in TOOL_CALLS:
        name, tool, args = scenario["name"], scenario["tool"], scenario["args"]
        if tool not in available:
            print(f"  [?] {name} ({tool}) — not exposed, skipping")
            continue
        ok, text = await _call(session, tool, args)
        status = "OK " if ok else "ERR"
        print(f"  [{status}] {name} ({tool})")
        if text:
            print(f"        {_preview(text)}")


async def main_async(args: argparse.Namespace) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    mcp_url = f"{args.mcp_url.rstrip('/')}/mcp"
    headers: Optional[dict[str, str]] = (
        {"Authorization": f"Bearer {args.token}"} if args.token else None
    )

    print(f"Connecting to {mcp_url} ...")
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            available = {t.name for t in tools}
            print(f"Connected — {len(tools)} tools available:")
            for t in sorted(available):
                print(f"  - {t}")
            print()

            pass_num = 0
            while True:
                pass_num += 1
                print(f"--- pass {pass_num} ---")
                await run_once(session, available)
                print()
                if not args.loop:
                    break
                await asyncio.sleep(args.interval)

    print("Done. Check the OpenObserve UI: http://localhost:5080 -> Logs -> 'default'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Feast MCP OTEL demo/test client")
    parser.add_argument("--mcp-url", default=MCP_URL, help="feast-mcp base URL")
    parser.add_argument("--token", default=None, help="Bearer token (if the server requires one)")
    parser.add_argument("--loop", action="store_true", help="Keep calling to generate traffic")
    parser.add_argument(
        "--interval", type=float, default=3.0, help="Seconds between passes when --loop is set"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
