"""Authorization tests for MCP endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from helpers import call_rest, get_token
from manifest import HttpMethod


SAMPLE_GET_ONLINE_PAYLOAD: dict[str, Any] = {
    "entities": {"driver_id": [1001]},
    "features": ["driver_hourly_stats:conv_rate"],
}


class TestFeatureServerAuth:
    """Authorization tests against the feature server."""

    def test_no_token_returns_401(self, auth_feature_server: str) -> None:
        """Request without Authorization header returns 401."""
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/get-online-features",
            method=HttpMethod.POST,
            payload=SAMPLE_GET_ONLINE_PAYLOAD,
            headers={},
        )
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, auth_feature_server: str) -> None:
        """Request with an invalid JWT returns 401."""
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/get-online-features",
            method=HttpMethod.POST,
            payload=SAMPLE_GET_ONLINE_PAYLOAD,
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert response.status_code == 401

    def test_insufficient_role_returns_403(
        self, auth_feature_server: str, mock_oidc_server: str
    ) -> None:
        """Valid token with role 'user' (no matching permission) returns 403."""
        token: str = get_token(mock_oidc_server, "user")
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/get-online-features",
            method=HttpMethod.POST,
            payload=SAMPLE_GET_ONLINE_PAYLOAD,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_admin_role_returns_200(
        self, auth_feature_server: str, mock_oidc_server: str
    ) -> None:
        """Valid token with role 'admin' returns 200."""
        token: str = get_token(mock_oidc_server, "admin")
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/get-online-features",
            method=HttpMethod.POST,
            payload=SAMPLE_GET_ONLINE_PAYLOAD,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_reader_role_can_read(
        self, auth_feature_server: str, mock_oidc_server: str
    ) -> None:
        """Valid token with role 'reader' can read online features (200)."""
        token: str = get_token(mock_oidc_server, "reader")
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/get-online-features",
            method=HttpMethod.POST,
            payload=SAMPLE_GET_ONLINE_PAYLOAD,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_reader_role_cannot_push(
        self, auth_feature_server: str, mock_oidc_server: str
    ) -> None:
        """Valid token with role 'reader' cannot push features (403)."""
        token: str = get_token(mock_oidc_server, "reader")
        push_payload: dict[str, Any] = {
            "push_source_name": "driver_stats_push",
            "df": {
                "driver_id": [9999],
                "conv_rate": [0.5],
                "acc_rate": [0.3],
                "avg_daily_trips": [10],
                "event_timestamp": ["2026-01-01T00:00:00"],
            },
            "to": "online",
        }
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/push",
            method=HttpMethod.POST,
            payload=push_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_health_endpoint_no_auth_required(self, auth_feature_server: str) -> None:
        """Health endpoint should work without auth."""
        response: httpx.Response = call_rest(
            base_url=auth_feature_server,
            endpoint="/health",
            method=HttpMethod.GET,
            headers={},
        )
        assert response.status_code == 200


class TestRegistryServerAuth:
    """Authorization tests against the registry server."""

    def test_no_token_returns_401(self, auth_registry_server: str) -> None:
        """Request without Authorization header returns 401."""
        response: httpx.Response = call_rest(
            base_url=auth_registry_server,
            endpoint="/entities",
            method=HttpMethod.GET,
            query_params={"project": "mcp_test_project"},
            headers={},
        )
        assert response.status_code == 401

    def test_admin_can_list_entities(
        self, auth_registry_server: str, mock_oidc_server: str
    ) -> None:
        """Admin can list entities."""
        token: str = get_token(mock_oidc_server, "admin")
        response: httpx.Response = call_rest(
            base_url=auth_registry_server,
            endpoint="/entities",
            method=HttpMethod.GET,
            query_params={"project": "mcp_test_project"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_insufficient_role_returns_403_on_registry(
        self, auth_registry_server: str, mock_oidc_server: str
    ) -> None:
        """User with no matching role gets 403 on registry."""
        token: str = get_token(mock_oidc_server, "user")
        response: httpx.Response = call_rest(
            base_url=auth_registry_server,
            endpoint="/entities",
            method=HttpMethod.GET,
            query_params={"project": "mcp_test_project"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
