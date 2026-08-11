"""Pytest fixtures for the MCP migration test suite.

Fixtures only — helper functions live in helpers.py.
Test files import helpers and manifest as top-level modules.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Ensure this directory is on sys.path so sibling modules (manifest,
# helpers, migration_report) are importable.  This must happen before
# the pytest_plugins declaration below, because pytest resolves plugin
# imports against sys.path very early in the bootstrap.
# ---------------------------------------------------------------------------

_TESTS_DIR: str = str(Path(__file__).parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# ---------------------------------------------------------------------------
# Register the migration report pytest plugin
# ---------------------------------------------------------------------------

pytest_plugins: list[str] = ["migration_report"]

# ---------------------------------------------------------------------------
# Port utilities
# ---------------------------------------------------------------------------


def free_port() -> int:
    """Bind to port 0 and return the assigned port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port: int = s.getsockname()[1]
        return port


def check_port_open(host: str, port: int) -> bool:
    """Check if a port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def wait_for_port(host: str, port: int, timeout_secs: int = 60) -> None:
    """Poll until a port is open or timeout."""
    deadline: float = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        if check_port_open(host, port):
            return
        time.sleep(0.5)
    raise TimeoutError(f"Port {port} on {host} not open after {timeout_secs}s")


# ---------------------------------------------------------------------------
# Feature repo setup fixture (session-scoped)
# ---------------------------------------------------------------------------

_FEATURE_REPO_SRC: Path = Path(__file__).parent / "feature_repo"


def _all_external_servers_set() -> bool:
    """Return True if all three external server env vars are set."""
    return bool(
        os.environ.get("FEAST_FEATURE_SERVER_URL")
        and os.environ.get("FEAST_REGISTRY_SERVER_URL")
        and os.environ.get("FEAST_MCP_SERVER_URL")
    )


@pytest.fixture(scope="session")
def feature_repo_path() -> Generator[Path, None, None]:
    """Copy the feature_repo to a temp dir, generate test data, run feast apply + materialize.

    Skipped entirely when all external server URLs are provided via env vars.
    """
    if _all_external_servers_set():
        yield Path("/dev/null")
        return

    tmp_dir: str = tempfile.mkdtemp(prefix="feast_mcp_test_")
    tmp_path: Path = Path(tmp_dir)

    dest: Path = tmp_path / "feature_repo"
    shutil.copytree(str(_FEATURE_REPO_SRC), str(dest))

    # Remove stale DB files that may have been copied from the source dir
    for stale in ("data/registry.db", "data/online_store.db"):
        (dest / stale).unlink(missing_ok=True)

    subprocess.run(
        ["python", "definitions.py"],
        cwd=str(dest),
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        ["feast", "-c", str(dest), "apply"],
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            "feast",
            "-c",
            str(dest),
            "materialize",
            "2025-01-01T00:00:00",
            "2027-01-01T00:00:00",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    yield dest

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature server fixture (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def feature_server(feature_repo_path: Path) -> Generator[str, None, None]:
    """Start feast serve as a subprocess, yield the base URL.

    Override with FEAST_FEATURE_SERVER_URL to use an external server.
    """
    external_url: str | None = os.environ.get("FEAST_FEATURE_SERVER_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    port: int = free_port()

    process: subprocess.Popen[bytes] = subprocess.Popen(
        [
            "feast",
            "-c",
            str(feature_repo_path),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
    )

    try:
        wait_for_port("localhost", port, timeout_secs=60)
    except TimeoutError:
        process.kill()
        raise

    base_url: str = f"http://localhost:{port}"
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


# ---------------------------------------------------------------------------
# Registry server fixture (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def registry_server(feature_repo_path: Path) -> Generator[str, None, None]:
    """Start feast serve_registry --rest-api as a subprocess, yield the base URL.

    Override with FEAST_REGISTRY_SERVER_URL to use an external server.
    The URL should include the /api/v1 prefix.
    """
    external_url: str | None = os.environ.get("FEAST_REGISTRY_SERVER_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    grpc_port: int = free_port()
    rest_port: int = free_port()

    process: subprocess.Popen[bytes] = subprocess.Popen(
        [
            "feast",
            "-c",
            str(feature_repo_path),
            "serve_registry",
            "--rest-api",
            "--port",
            str(grpc_port),
            "--rest-port",
            str(rest_port),
        ],
    )

    try:
        wait_for_port("localhost", rest_port, timeout_secs=60)
    except TimeoutError:
        process.kill()
        raise

    base_url: str = f"http://localhost:{rest_port}/api/v1"
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


# ---------------------------------------------------------------------------
# Standalone MCP server fixture (session-scoped)
# ---------------------------------------------------------------------------

_MCP_SERVER_MODULE: str = "feast_mcp.server"


@pytest.fixture(scope="session")
def mcp_server(feature_server: str) -> Generator[str, None, None]:
    """Start the standalone Feast MCP server as a subprocess.

    The MCP server is a proxy — it forwards tool calls to the upstream
    Feast feature server over HTTP.  It runs on its own port with SSE
    transport.

    Override with FEAST_MCP_SERVER_URL to use an external server.
    """
    external_url: str | None = os.environ.get("FEAST_MCP_SERVER_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    port: int = free_port()

    process: subprocess.Popen[bytes] = subprocess.Popen(
        [
            "python",
            "-m",
            _MCP_SERVER_MODULE,
            "--feast-url",
            feature_server,
            "--transport",
            "streamable-http",
            "--port",
            str(port),
        ],
    )

    try:
        wait_for_port("localhost", port, timeout_secs=60)
    except TimeoutError:
        process.kill()
        raise

    base_url: str = f"http://localhost:{port}"
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

_FEAST_REPO_ROOT: Path = Path(__file__).parent.parent.parent
_MOCK_OIDC_SCRIPT: Path = (
    _FEAST_REPO_ROOT / "examples" / "mcp_auth_feature_store" / "mock_oidc_server.py"
)


@pytest.fixture(scope="session")
def mock_oidc_server() -> Generator[str, None, None]:
    """Start the mock OIDC server as a subprocess.

    Override with FEAST_MOCK_OIDC_URL to use an external OIDC server.
    """
    external_url: str | None = os.environ.get("FEAST_MOCK_OIDC_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    port: int = free_port()

    process: subprocess.Popen[bytes] = subprocess.Popen(
        ["python", str(_MOCK_OIDC_SCRIPT), str(port)],
    )

    try:
        wait_for_port("127.0.0.1", port, timeout_secs=30)
    except TimeoutError:
        process.kill()
        raise

    base_url: str = f"http://127.0.0.1:{port}"
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="session")
def auth_feature_repo_path(
    mock_oidc_server: str,
) -> Generator[Path, None, None]:
    """Create a feature repo with OIDC auth config."""
    tmp_dir: str = tempfile.mkdtemp(prefix="feast_mcp_auth_test_")
    tmp_path: Path = Path(tmp_dir)

    dest: Path = tmp_path / "feature_repo"
    shutil.copytree(str(_FEATURE_REPO_SRC), str(dest))

    for stale in ("data/registry.db", "data/online_store.db"):
        (dest / stale).unlink(missing_ok=True)

    subprocess.run(
        ["python", "definitions.py"],
        cwd=str(dest),
        check=True,
        capture_output=True,
        text=True,
    )

    auth_yaml: str = (
        f"project: mcp_test_project\n"
        f"provider: local\n"
        f"registry:\n"
        f"  path: data/registry.db\n"
        f"online_store:\n"
        f"  type: sqlite\n"
        f"  path: data/online_store.db\n"
        f"offline_store:\n"
        f"  type: file\n"
        f"feature_server:\n"
        f"  type: mcp\n"
        f"  enabled: true\n"
        f"  mcp_enabled: true\n"
        f"  mcp_transport: http\n"
        f'  mcp_server_name: "feast-mcp-test"\n'
        f'  mcp_server_version: "1.0.0"\n'
        f"  feature_logging:\n"
        f"    enabled: false\n"
        f"entity_key_serialization_version: 3\n"
        f"auth:\n"
        f"  type: oidc\n"
        f'  auth_discovery_url: "{mock_oidc_server}/.well-known/openid-configuration"\n'
        f'  client_id: "feast-demo"\n'
    )
    yaml_path: Path = dest / "feature_store.yaml"
    yaml_path.write_text(auth_yaml)

    subprocess.run(
        ["feast", "-c", str(dest), "apply"],
        check=True,
        capture_output=True,
        text=True,
    )

    yield dest

    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def auth_feature_server(
    auth_feature_repo_path: Path,
) -> Generator[str, None, None]:
    """Start feast serve with OIDC auth.

    Override with FEAST_AUTH_FEATURE_SERVER_URL to use an external server.
    """
    external_url: str | None = os.environ.get("FEAST_AUTH_FEATURE_SERVER_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    port: int = free_port()

    process: subprocess.Popen[bytes] = subprocess.Popen(
        [
            "feast",
            "-c",
            str(auth_feature_repo_path),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
    )

    try:
        wait_for_port("localhost", port, timeout_secs=60)
    except TimeoutError:
        process.kill()
        raise

    base_url: str = f"http://localhost:{port}"
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="session")
def auth_registry_server(
    auth_feature_repo_path: Path,
) -> Generator[str, None, None]:
    """Start feast serve_registry with OIDC auth.

    Override with FEAST_AUTH_REGISTRY_SERVER_URL to use an external server.
    The URL should include the /api/v1 prefix.
    """
    external_url: str | None = os.environ.get("FEAST_AUTH_REGISTRY_SERVER_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    grpc_port: int = free_port()
    rest_port: int = free_port()

    process: subprocess.Popen[bytes] = subprocess.Popen(
        [
            "feast",
            "-c",
            str(auth_feature_repo_path),
            "serve_registry",
            "--rest-api",
            "--port",
            str(grpc_port),
            "--rest-port",
            str(rest_port),
        ],
    )

    try:
        wait_for_port("localhost", rest_port, timeout_secs=60)
    except TimeoutError:
        process.kill()
        raise

    base_url: str = f"http://localhost:{rest_port}/api/v1"
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
