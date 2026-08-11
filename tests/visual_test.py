"""Side-by-side comparison of REST vs MCP responses.

Usage:
    python tests/visual_test.py                              # defaults
    python tests/visual_test.py --feast-url http://host:6566 --mcp-url http://host:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
from typing import Any

import httpx

from helpers import call_mcp_tool, extract_path_and_query_params
from manifest import FEATURE_SERVER_TOOLS, HttpMethod, ToolTestSpec

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

COLUMN_WIDTH: int = 60
SEPARATOR: str = "─"
DIVIDER: str = "│"

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def _wrap_lines(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        if len(raw_line) <= width:
            lines.append(raw_line)
        else:
            lines.extend(textwrap.wrap(raw_line, width=width))
    return lines if lines else [""]


def _pretty_json(data: Any, width: int) -> list[str]:
    try:
        formatted: str = json.dumps(data, indent=2, default=str)
    except (TypeError, ValueError):
        formatted = str(data)
    return _wrap_lines(formatted, width)


def _print_header(title: str) -> None:
    full_width: int = COLUMN_WIDTH * 2 + 3
    print()
    print(f"{BOLD}{CYAN}{SEPARATOR * full_width}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{SEPARATOR * full_width}{RESET}")


def _print_columns(left_title: str, right_title: str) -> None:
    print(
        f"  {BOLD}{left_title:<{COLUMN_WIDTH}}{RESET} {DIVIDER} "
        f"{BOLD}{right_title:<{COLUMN_WIDTH}}{RESET}"
    )
    print(f"  {SEPARATOR * COLUMN_WIDTH} {DIVIDER} {SEPARATOR * COLUMN_WIDTH}")


def _print_side_by_side(
    left_lines: list[str], right_lines: list[str]
) -> None:
    max_lines: int = max(len(left_lines), len(right_lines))
    for i in range(max_lines):
        left: str = left_lines[i] if i < len(left_lines) else ""
        right: str = right_lines[i] if i < len(right_lines) else ""
        print(f"  {left:<{COLUMN_WIDTH}} {DIVIDER} {right:<{COLUMN_WIDTH}}")


def _print_status(label: str, status: int | str, color: str) -> str:
    return f"{color}{label}: {status}{RESET}"


def _print_match_result(match: bool) -> None:
    if match:
        print(f"\n  {GREEN}{BOLD}✔ MATCH{RESET}")
    else:
        print(f"\n  {RED}{BOLD}✘ MISMATCH{RESET}")


# ---------------------------------------------------------------------------
# REST call
# ---------------------------------------------------------------------------


def call_rest_raw(
    base_url: str,
    endpoint: str,
    method: HttpMethod,
    payload: dict[str, Any] | None = None,
    query_params: dict[str, str] | None = None,
) -> tuple[int, Any]:
    resolved: str = base_url + endpoint
    with httpx.Client(timeout=30.0) as client:
        if method in (HttpMethod.GET, HttpMethod.DELETE):
            resp: httpx.Response = client.request(
                method.value, resolved, params=query_params
            )
        else:
            resp = client.request(method.value, resolved, json=payload)
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body


# ---------------------------------------------------------------------------
# MCP call
# ---------------------------------------------------------------------------


async def call_mcp_raw(
    mcp_url: str, tool_name: str, args: dict[str, Any]
) -> tuple[str, Any]:
    try:
        result: Any = await call_mcp_tool(mcp_url, tool_name, args)
        if hasattr(result, "isError") and result.isError:
            return "ERROR", str(result)
        if hasattr(result, "content"):
            text_parts: list[str] = [
                p.text for p in result.content if hasattr(p, "text")
            ]
            raw: str = "".join(text_parts)
            try:
                return "OK", json.loads(raw)
            except json.JSONDecodeError:
                return "OK", raw
        return "OK", result
    except Exception as exc:
        return "ERROR", str(exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual REST vs MCP comparison")
    parser.add_argument(
        "--feast-url", default="http://localhost:6566", help="Feast feature server URL"
    )
    parser.add_argument(
        "--mcp-url", default="http://localhost:8000", help="MCP server URL"
    )
    parser.add_argument(
        "--tool", default=None, help="Run only this tool (by name)"
    )
    args = parser.parse_args()

    feast_url: str = args.feast_url.rstrip("/")
    mcp_url: str = args.mcp_url.rstrip("/") + "/mcp"

    specs: list[ToolTestSpec] = FEATURE_SERVER_TOOLS
    if args.tool:
        specs = [s for s in specs if s.tool_name == args.tool]
        if not specs:
            print(f"{RED}No tool found with name '{args.tool}'{RESET}")
            sys.exit(1)

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = []

    print(f"\n{BOLD}Feast Feature Server:{RESET} {feast_url}")
    print(f"{BOLD}MCP Server:{RESET}           {mcp_url}")

    for spec in specs:
        if spec.skip_reason:
            _print_header(f"SKIP  {spec.tool_name}")
            print(f"  {YELLOW}{spec.skip_reason}{RESET}")
            skipped += 1
            continue

        if not spec.migrated:
            _print_header(f"SKIP  {spec.tool_name} (not migrated)")
            skipped += 1
            continue

        sample: dict[str, Any] = spec.sample_inputs[0]
        endpoint, body, qparams = extract_path_and_query_params(
            spec.feast_endpoint, sample
        )

        _print_header(f"{spec.tool_name}  →  {spec.http_method.value} {endpoint}")

        # REST
        rest_status, rest_body = call_rest_raw(
            feast_url,
            endpoint,
            spec.http_method,
            payload=body if spec.http_method == HttpMethod.POST else None,
            query_params=qparams if spec.http_method != HttpMethod.POST else None,
        )

        # MCP
        mcp_status, mcp_body = asyncio.run(
            call_mcp_raw(mcp_url, spec.tool_name, sample)
        )

        # Status line
        rest_color: str = GREEN if rest_status == 200 else RED
        mcp_color: str = GREEN if mcp_status == "OK" else RED
        print(
            f"  {_print_status('REST', rest_status, rest_color)}"
            f"    {_print_status('MCP', mcp_status, mcp_color)}"
        )
        print()

        # Side-by-side body
        _print_columns("REST Response", "MCP Response")

        rest_lines: list[str] = _pretty_json(rest_body, COLUMN_WIDTH)
        mcp_lines: list[str] = _pretty_json(mcp_body, COLUMN_WIDTH)

        _print_side_by_side(rest_lines, mcp_lines)

        # Match check (non-mutation only)
        if not spec.mutation:
            try:
                rest_norm = json.loads(json.dumps(rest_body, sort_keys=True, default=str))
                mcp_norm = json.loads(json.dumps(mcp_body, sort_keys=True, default=str))
                match: bool = rest_norm == mcp_norm
            except Exception:
                match = str(rest_body) == str(mcp_body)
            _print_match_result(match)
            if match:
                passed += 1
            else:
                failed += 1
                errors.append(spec.tool_name)
        else:
            if mcp_status == "OK":
                print(f"\n  {GREEN}{BOLD}✔ MCP mutation succeeded{RESET}")
                passed += 1
            else:
                print(f"\n  {RED}{BOLD}✘ MCP mutation failed{RESET}")
                failed += 1
                errors.append(spec.tool_name)

    # Summary
    full_width: int = COLUMN_WIDTH * 2 + 3
    print(f"\n{BOLD}{SEPARATOR * full_width}{RESET}")
    print(
        f"  {BOLD}Results:{RESET}  "
        f"{GREEN}{passed} passed{RESET}  "
        f"{RED}{failed} failed{RESET}  "
        f"{YELLOW}{skipped} skipped{RESET}  "
        f"({passed + failed + skipped} total)"
    )
    if errors:
        print(f"  {RED}Failed:{RESET} {', '.join(errors)}")
    print(f"{BOLD}{SEPARATOR * full_width}{RESET}\n")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
