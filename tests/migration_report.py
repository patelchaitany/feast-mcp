"""Pytest plugin: prints MCP migration status after test run."""

from __future__ import annotations

from typing import Any

import pytest

from manifest import (
    FEATURE_SERVER_TOOLS,
    REGISTRY_TOOLS,
    ToolTestSpec,
)


class MigrationReportPlugin:
    """Collects test results and prints the migration checklist."""

    def __init__(self) -> None:
        self._results: dict[
            str, str
        ] = {}  # tool_name -> "passed" | "failed" | "skipped"

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report: Any) -> None:
        """Capture test outcomes keyed by tool_name."""
        if report.when != "call":
            return
        # Extract tool_name from parametrize ID (e.g. "...::test_foo[get_online_features]")
        node_id: str = report.nodeid
        if "[" in node_id and "]" in node_id:
            tool_name: str = node_id.split("[")[1].rstrip("]")
            if report.passed:
                self._results[tool_name] = "passed"
            elif report.failed:
                self._results[tool_name] = "failed"
            else:
                self._results[tool_name] = "skipped"

    def pytest_terminal_summary(
        self,
        terminalreporter: Any,
        exitstatus: int,
        config: Any,
    ) -> None:
        """Print the migration status checklist."""
        terminalreporter.section("FEAST MCP MIGRATION STATUS")

        # Print feature server section
        _print_server_section(
            terminalreporter,
            "FEATURE SERVER",
            FEATURE_SERVER_TOOLS,
            self._results,
        )

        terminalreporter.write_line("")

        # Print registry server section
        _print_server_section(
            terminalreporter,
            "REGISTRY SERVER",
            REGISTRY_TOOLS,
            self._results,
        )

        # Print totals
        all_tools: list[ToolTestSpec] = FEATURE_SERVER_TOOLS + REGISTRY_TOOLS
        total: int = len(all_tools)
        migrated: int = sum(1 for t in all_tools if t.migrated)
        passed: int = sum(
            1
            for t in all_tools
            if t.migrated and self._results.get(t.tool_name) == "passed"
        )
        failed: int = sum(
            1
            for t in all_tools
            if t.migrated and self._results.get(t.tool_name) == "failed"
        )
        pct: float = (migrated / total * 100) if total > 0 else 0.0

        terminalreporter.write_line("")
        terminalreporter.write_line(f"TOTAL: {migrated}/{total} migrated ({pct:.1f}%)")
        if passed > 0:
            terminalreporter.write_line(f"  PASSED: {passed}")
        if failed > 0:
            terminalreporter.write_line(f"  FAILED: {failed}")


def _print_server_section(
    writer: Any,
    title: str,
    tools: list[ToolTestSpec],
    results: dict[str, str],
) -> None:
    """Print a server section of the migration report."""
    total: int = len(tools)
    migrated: int = sum(1 for t in tools if t.migrated)
    writer.write_line(f"{title} ({migrated}/{total} migrated)")
    writer.write_line("-" * 72)

    for tool in tools:
        method_str: str = tool.http_method.value.ljust(6)
        endpoint_str: str = tool.feast_endpoint.ljust(45)
        tool_name_str: str = tool.tool_name.ljust(35)

        if not tool.migrated:
            status: str = "[ ]"
            detail: str = "(not migrated)"
        else:
            result: str = results.get(tool.tool_name, "unknown")
            if result == "passed":
                status = "[+]"
                detail = "PASS"
            elif result == "failed":
                status = "[X]"
                detail = "FAIL"
            else:
                status = "[?]"
                detail = result

        writer.write_line(
            f"  {status} {tool_name_str} -> {method_str} {endpoint_str} {detail}"
        )


def pytest_configure(config: Any) -> None:
    """Register the migration report plugin (only if not already registered)."""
    if not config.pluginmanager.has_plugin("migration_report"):
        plugin: MigrationReportPlugin = MigrationReportPlugin()
        config.pluginmanager.register(plugin, "migration_report")
