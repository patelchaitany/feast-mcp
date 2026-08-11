"""
Lightweight mock OIDC provider for the Feast MCP OIDC demo.

Serves the endpoints that both the Feast OidcTokenParser and the
FastMCP OIDCProxy need:

  - /.well-known/openid-configuration  (discovery)
  - /jwks                              (JSON Web Key Set)
  - /token                             (password, client_credentials, authorization_code)
  - /authorize                         (authorization code flow — browser redirect)
  - /register                          (dynamic client registration — RFC 7591)

Generates an RSA key pair at startup and signs JWTs with it.
NOT for production use -- this is a demo-only tool.

Usage:
    python mock_oidc_server.py          # starts on port 8081
    python mock_oidc_server.py 9090     # custom port
"""

import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
CLIENT_ID = "feast-demo"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

_pub_numbers = _public_key.public_numbers()


def _int_to_base64url(n: int) -> str:
    byte_length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()


JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "demo-key-1",
            "alg": "RS256",
            "n": _int_to_base64url(_pub_numbers.n),
            "e": _int_to_base64url(_pub_numbers.e),
        }
    ]
}

USERS = {
    "admin": {"password": "admin", "roles": ["admin"]},
    "reader": {"password": "reader", "roles": ["reader"]},
    "user": {"password": "user", "roles": ["user"]},
}

# In-memory stores for authorization code flow and dynamic client registration
_auth_codes: dict[str, dict] = {}
_registered_clients: dict[str, dict] = {}


def _make_token(username: str, roles: list[str]) -> str:
    now = int(time.time())
    claims = {
        "iss": f"http://{HOST}:{PORT}",
        "sub": username,
        "aud": CLIENT_ID,
        "preferred_username": username,
        "resource_access": {CLIENT_ID: {"roles": roles}},
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(claims, _private_pem, algorithm="RS256", headers={"kid": "demo-key-1"})


def _parse_query(path: str) -> tuple[str, dict[str, str]]:
    parsed = urllib.parse.urlparse(path)
    params = dict(urllib.parse.parse_qsl(parsed.query))
    return parsed.path, params


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return computed == code_challenge
    return code_verifier == code_challenge


class OIDCHandler(BaseHTTPRequestHandler):
    def _respond(self, status: int, body: dict | str, content_type: str = "application/json") -> None:
        payload = (json.dumps(body) if isinstance(body, dict) else body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _respond_html(self, status: int, html: str) -> None:
        payload = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        path, query_params = _parse_query(self.path)

        if path == "/.well-known/openid-configuration":
            base = f"http://{HOST}:{PORT}"
            self._respond(200, {
                "issuer": base,
                "authorization_endpoint": f"{base}/authorize",
                "token_endpoint": f"{base}/token",
                "registration_endpoint": f"{base}/register",
                "jwks_uri": f"{base}/jwks",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "client_credentials", "password"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
                "code_challenge_methods_supported": ["S256", "plain"],
                "scopes_supported": ["openid", "profile", "email"],
            })

        elif path == "/jwks":
            self._respond(200, JWKS)

        elif path == "/authorize":
            redirect_uri = query_params.get("redirect_uri", "")
            state = query_params.get("state", "")
            code_challenge = query_params.get("code_challenge", "")
            code_challenge_method = query_params.get("code_challenge_method", "plain")

            self._respond_html(200, f"""<!DOCTYPE html>
<html><head><title>Mock OIDC Login</title></head>
<body style="font-family:sans-serif; max-width:400px; margin:60px auto;">
  <h2>Mock OIDC Login</h2>
  <form method="POST" action="/authorize">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="code_challenge" value="{code_challenge}">
    <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
    <label>Username<br><input name="username" value="admin" style="width:100%;padding:8px;"></label><br><br>
    <label>Password<br><input name="password" type="password" value="admin" style="width:100%;padding:8px;"></label><br><br>
    <button type="submit" style="padding:10px 24px;">Sign in</button>
  </form>
  <p style="color:#888;font-size:12px;">Users: admin/admin, reader/reader, user/user</p>
</body></html>""")

        else:
            self._respond(404, {"error": "not_found"})

    def _parse_client_auth(self, params: dict) -> tuple[str | None, str | None]:
        """Extract client_id/client_secret from Basic auth header or body params."""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            decoded = base64.b64decode(auth_header[6:]).decode()
            client_id, _, client_secret = decoded.partition(":")
            return (
                urllib.parse.unquote(client_id),
                urllib.parse.unquote(client_secret),
            )
        return params.get("client_id"), params.get("client_secret")

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        path, _ = _parse_query(self.path)

        if path == "/authorize":
            params = dict(urllib.parse.parse_qsl(body))
            username = params.get("username", "")
            password = params.get("password", "")
            redirect_uri = params.get("redirect_uri", "")
            state = params.get("state", "")
            code_challenge = params.get("code_challenge", "")
            code_challenge_method = params.get("code_challenge_method", "plain")

            user = USERS.get(username)
            if not user or user["password"] != password:
                self._respond_html(401, "<h2>Invalid credentials</h2><p><a href='javascript:history.back()'>Try again</a></p>")
                return

            code = secrets.token_urlsafe(32)
            _auth_codes[code] = {
                "username": username,
                "roles": user["roles"],
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "created_at": time.time(),
            }

            redirect = f"{redirect_uri}?code={code}"
            if state:
                redirect += f"&state={urllib.parse.quote(state)}"
            self._redirect(redirect)

        elif path == "/token":
            params = dict(urllib.parse.parse_qsl(body))
            client_id, client_secret = self._parse_client_auth(params)
            grant_type = params.get("grant_type", "")

            print(f"  [OIDC] Token request: grant_type={grant_type}, "
                  f"client_id={client_id}, "
                  f"has_code={bool(params.get('code'))}, "
                  f"has_verifier={bool(params.get('code_verifier'))}")

            if grant_type == "authorization_code":
                code = params.get("code", "")
                code_data = _auth_codes.pop(code, None)
                if not code_data:
                    print(f"  [OIDC] Invalid code. Active codes: {list(_auth_codes.keys())}")
                    self._respond(400, {"error": "invalid_grant", "error_description": "Invalid or expired authorization code"})
                    return

                if time.time() - code_data["created_at"] > 300:
                    self._respond(400, {"error": "invalid_grant", "error_description": "Authorization code expired"})
                    return

                if code_data["code_challenge"]:
                    code_verifier = params.get("code_verifier", "")
                    if not code_verifier or not _verify_pkce(code_verifier, code_data["code_challenge"], code_data["code_challenge_method"]):
                        print(f"  [OIDC] PKCE failed: verifier={code_verifier[:20] if code_verifier else 'MISSING'}...")
                        self._respond(400, {"error": "invalid_grant", "error_description": "PKCE verification failed"})
                        return

                token = _make_token(code_data["username"], code_data["roles"])
                self._respond(200, {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                })

            elif grant_type == "client_credentials":
                token = _make_token("admin", ["admin"])
                self._respond(200, {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                })

            elif grant_type == "password":
                username = params.get("username", "admin")
                password = params.get("password", "")
                user = USERS.get(username)
                if user and user["password"] == password:
                    token = _make_token(username, user["roles"])
                    self._respond(200, {
                        "access_token": token,
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    })
                else:
                    self._respond(401, {"error": "invalid_credentials"})

            else:
                self._respond(400, {"error": "unsupported_grant_type"})

        elif path == "/register":
            client_data = json.loads(body) if body else {}
            client_id = f"dyn-{secrets.token_hex(8)}"
            client_secret = secrets.token_hex(16)
            _registered_clients[client_id] = {
                "client_id": client_id,
                "client_secret": client_secret,
                **client_data,
            }
            self._respond(201, {
                "client_id": client_id,
                "client_secret": client_secret,
                "client_id_issued_at": int(time.time()),
                "client_secret_expires_at": 0,
                **{k: v for k, v in client_data.items() if k in (
                    "redirect_uris", "grant_types", "response_types",
                    "token_endpoint_auth_method", "client_name",
                )},
            })

        else:
            self._respond(404, {"error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"  [OIDC] {args[0]}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main() -> None:
    server = ThreadedHTTPServer((HOST, PORT), OIDCHandler)
    print(f"Mock OIDC server running on http://{HOST}:{PORT}")
    print(f"  Discovery:    http://{HOST}:{PORT}/.well-known/openid-configuration")
    print(f"  JWKS:         http://{HOST}:{PORT}/jwks")
    print(f"  Token:        http://{HOST}:{PORT}/token")
    print(f"  Authorize:    http://{HOST}:{PORT}/authorize")
    print(f"  Register:     http://{HOST}:{PORT}/register  (dynamic client registration)")
    print(f"  Users:        admin (roles: [admin]), reader (roles: [reader]), user (roles: [user])")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
