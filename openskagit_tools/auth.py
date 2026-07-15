from __future__ import annotations

import secrets

from mcp.server.auth.provider import AccessToken

READ_SCOPE = "openskagit.read"
MINIMUM_TOKEN_LENGTH = 32


class StaticBearerTokenVerifier:
    """Verify one deployment-provided bearer token using constant-time comparison.

    This is the first remote-transport authentication boundary. It intentionally
    supports only a read scope and never logs or exposes the configured secret.
    A managed OAuth/OIDC verifier can replace it without changing tool handlers.
    """

    def __init__(self, expected_token: str, *, client_id: str = "openskagit-mcp-client") -> None:
        token = expected_token.strip()
        if len(token) < MINIMUM_TOKEN_LENGTH:
            raise ValueError(f"MCP bearer token must contain at least {MINIMUM_TOKEN_LENGTH} characters.")
        self._expected_token = token
        self._client_id = client_id

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or not secrets.compare_digest(token, self._expected_token):
            return None
        return AccessToken(
            token=token,
            client_id=self._client_id,
            scopes=[READ_SCOPE],
            subject=self._client_id,
            claims={"auth_method": "static_bearer"},
        )
