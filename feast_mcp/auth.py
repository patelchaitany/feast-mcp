"""Authorization helpers for the Feast MCP server.

The MCP server does not enforce its own RBAC — it forwards the caller's
bearer token to the upstream Feast feature server, which validates the
token (OIDC / Kubernetes SA token) and applies its own permission model.

Two modes are supported:

1. **No auth** (default, or ``--auth-mode passthrough``):
   No authentication required — connections are accepted without tokens.
   Useful for development or when the client already holds a valid token.

2. **OIDC login** (``--auth-mode oidc``):
   An OIDCProxy discovers endpoints from the OIDC discovery URL
   (the same ``auth_discovery_url`` used in Feast's feature_store.yaml)
   and presents a browser login flow so that IDE clients (Cursor, VS Code,
   etc.) can sign the user in.  After login the upstream access token is
   stored server-side and forwarded to Feast on every tool call.

   Programmatic clients (MCP SDK, demo scripts) can also send OIDC
   provider tokens directly as Bearer tokens — the server validates them
   against the provider's JWKS as a fallback.
"""

from typing import Optional

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class FeastOIDCProxy(OIDCProxy):
    """OIDCProxy that also accepts direct OIDC provider tokens.

    IDE clients go through the full OAuth flow and get MCP-issued JWTs.
    Programmatic clients (MCP SDK, scripts) can send OIDC provider tokens
    directly — they are validated against the provider's JWKS as a fallback.
    """

    async def load_access_token(self, token: str) -> AccessToken | None:
        # Step 1: Try MCP-issued JWT validation (IDE OAuth flow tokens)
        result = await super().load_access_token(token)
        if result is not None:
            return result

        # Step 2: Try direct OIDC provider token validation (SDK clients)
        # _token_validator is a JWTVerifier configured with the OIDC
        # provider's JWKS URI (e.g. http://keycloak:8081/jwks)
        try:
            logger.debug("MCP JWT validation failed, trying direct OIDC provider token")
            validated = await self._token_validator.verify_token(token)
            if validated is not None:
                logger.debug("Direct OIDC provider token accepted for sub=%s", validated.claims.get("sub"))
            return validated
        except Exception as e:
            logger.debug("Direct OIDC provider token validation also failed: %s", e)
            return None


def create_oidc_auth(
    *,
    discovery_url: str,
    client_id: str,
    client_secret: Optional[str] = None,
    base_url: str,
    audience: Optional[str] = None,
) -> FeastOIDCProxy:
    return FeastOIDCProxy(
        config_url=discovery_url,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        audience=audience,
    )


def get_auth_token() -> Optional[str]:
    access_token: Optional[AccessToken] = get_access_token()
    if access_token is None:
        return None
    return access_token.token
