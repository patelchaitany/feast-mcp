"""Coverage cross-check: verify manifest covers all server endpoints."""

from __future__ import annotations

import warnings
from typing import Set, Tuple

from helpers import auto_discover_endpoints
from manifest import (
    FEATURE_SERVER_TOOLS,
    REGISTRY_TOOLS,
    DiscoveredEndpoint,
    ServerType,
)

SKIP_PATHS: set[str] = {"/docs", "/openapi.json", "/redoc"}


def _format_endpoint_set(endpoints: Set[Tuple[str, str]]) -> str:
    sorted_endpoints: list[Tuple[str, str]] = sorted(endpoints)
    lines: list[str] = [f"  {method:>6}  {path}" for path, method in sorted_endpoints]
    return "\n" + "\n".join(lines)


def test_feature_server_endpoint_coverage(feature_server: str) -> None:
    """Warn if any feature server endpoint is missing from the manifest."""
    discovered: list[DiscoveredEndpoint] = auto_discover_endpoints(
        f"{feature_server}/openapi.json", ServerType.FEATURE_SERVER
    )
    manifest_set: set[tuple[str, str]] = {
        (t.feast_endpoint, t.http_method.value) for t in FEATURE_SERVER_TOOLS
    }
    discovered_set: set[tuple[str, str]] = {
        (d.path, d.method)
        for d in discovered
        if d.path not in SKIP_PATHS
    }

    uncovered: set[tuple[str, str]] = discovered_set - manifest_set
    stale: set[tuple[str, str]] = manifest_set - discovered_set

    if uncovered:
        warnings.warn(
            f"UNCOVERED feature server endpoints (need ToolTestSpec):"
            f"{_format_endpoint_set(uncovered)}",
            stacklevel=1,
        )
    if stale:
        warnings.warn(
            f"STALE feature server manifest entries (endpoint removed):"
            f"{_format_endpoint_set(stale)}",
            stacklevel=1,
        )


def test_registry_endpoint_coverage(registry_server: str) -> None:
    """Warn if any registry endpoint is missing from the manifest."""
    base_url: str = registry_server.replace("/api/v1", "")
    discovered: list[DiscoveredEndpoint] = auto_discover_endpoints(
        f"{base_url}/api/v1/openapi.json", ServerType.REGISTRY
    )

    # OpenAPI returns paths without the /api/v1 prefix, but the manifest
    # includes it.  Normalize discovered paths to include the prefix.
    discovered_set: set[tuple[str, str]] = {
        (f"/api/v1{d.path}", d.method)
        for d in discovered
        if d.path not in SKIP_PATHS
    }
    manifest_set: set[tuple[str, str]] = {
        (t.feast_endpoint, t.http_method.value) for t in REGISTRY_TOOLS
    }

    uncovered: set[tuple[str, str]] = discovered_set - manifest_set
    stale: set[tuple[str, str]] = manifest_set - discovered_set

    if uncovered:
        warnings.warn(
            f"UNCOVERED registry endpoints (need ToolTestSpec):"
            f"{_format_endpoint_set(uncovered)}",
            stacklevel=1,
        )
    if stale:
        warnings.warn(
            f"STALE registry manifest entries (endpoint removed):"
            f"{_format_endpoint_set(stale)}",
            stacklevel=1,
        )
