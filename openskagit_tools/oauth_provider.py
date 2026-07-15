from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .auth import READ_SCOPE
from .models import (
    McpOAuthAuthorizationCode,
    McpOAuthClient,
    McpOAuthGrant,
    token_digest,
)

ACCESS_TTL_SECONDS = 60 * 60
REFRESH_TTL_SECONDS = 60 * 60 * 24 * 30
CODE_TTL_SECONDS = 5 * 60


class DjangoOAuthProvider:
    """Persistent OAuth authorization provider for approved OpenSkagit clients."""

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return await sync_to_async(self._get_client, thread_sensitive=True)(client_id)

    @staticmethod
    def _get_client(client_id: str) -> OAuthClientInformationFull | None:
        try:
            row = McpOAuthClient.objects.select_related("access_request").get(client_id=client_id)
        except McpOAuthClient.DoesNotExist:
            return None
        if not row.is_available:
            return None
        return OAuthClientInformationFull(
            client_id=row.client_id,
            client_secret=row.get_client_secret(),
            client_id_issued_at=int(row.created_at.timestamp()),
            client_secret_expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
            client_name=row.name,
            redirect_uris=row.redirect_uris,
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=row.scope,
            contacts=[row.access_request.email] if row.access_request else None,
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise RegistrationError(error="unapproved_software_statement", error_description="Access approval is required.")

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        requested_scopes = params.scopes or [READ_SCOPE]
        if set(requested_scopes) - {READ_SCOPE}:
            raise AuthorizeError(error="invalid_scope", error_description="Only openskagit.read is available.")
        raw_code = secrets.token_urlsafe(32)
        subject = client.client_id or "approved-client"
        await sync_to_async(self._create_authorization_code, thread_sensitive=True)(
            client.client_id,
            code_digest=token_digest(raw_code),
            scopes=requested_scopes,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            subject=subject,
            expires_at=timezone.now() + timedelta(seconds=CODE_TTL_SECONDS),
        )
        return construct_redirect_uri(str(params.redirect_uri), code=raw_code, state=params.state)

    @staticmethod
    def _create_authorization_code(client_id: str | None, **values: Any) -> McpOAuthAuthorizationCode:
        client_row = McpOAuthClient.objects.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).get(client_id=client_id, active=True)
        return McpOAuthAuthorizationCode.objects.create(client=client_row, **values)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return await sync_to_async(self._load_authorization_code, thread_sensitive=True)(
            client.client_id, authorization_code
        )

    @staticmethod
    def _load_authorization_code(client_id: str | None, raw_code: str) -> AuthorizationCode | None:
        try:
            row = McpOAuthAuthorizationCode.objects.select_related("client").filter(
                Q(client__expires_at__isnull=True) | Q(client__expires_at__gt=timezone.now())
            ).get(
                client__client_id=client_id,
                client__active=True,
                code_digest=token_digest(raw_code),
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        except McpOAuthAuthorizationCode.DoesNotExist:
            return None
        return AuthorizationCode(
            code=raw_code,
            client_id=row.client.client_id,
            scopes=row.scopes,
            expires_at=row.expires_at.timestamp(),
            code_challenge=row.code_challenge,
            redirect_uri=row.redirect_uri,
            redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
            subject=row.subject,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        return await sync_to_async(self._exchange_authorization_code, thread_sensitive=True)(
            client.client_id, authorization_code
        )

    @staticmethod
    @transaction.atomic
    def _exchange_authorization_code(client_id: str | None, authorization_code: AuthorizationCode) -> OAuthToken:
        try:
            row = McpOAuthAuthorizationCode.objects.select_for_update().select_related("client").filter(
                Q(client__expires_at__isnull=True) | Q(client__expires_at__gt=timezone.now())
            ).get(
                client__client_id=client_id,
                client__active=True,
                code_digest=token_digest(authorization_code.code),
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        except McpOAuthAuthorizationCode.DoesNotExist as exc:
            raise TokenError(error="invalid_grant", error_description="Authorization code is invalid or expired.") from exc
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        return DjangoOAuthProvider._issue_grant(row.client, row.scopes, row.subject)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return await sync_to_async(self._load_refresh_token, thread_sensitive=True)(client.client_id, refresh_token)

    @staticmethod
    def _load_refresh_token(client_id: str | None, raw_token: str) -> RefreshToken | None:
        try:
            row = McpOAuthGrant.objects.select_related("client").filter(
                Q(client__expires_at__isnull=True) | Q(client__expires_at__gt=timezone.now())
            ).get(
                client__client_id=client_id,
                client__active=True,
                refresh_token_digest=token_digest(raw_token),
                active=True,
                refresh_expires_at__gt=timezone.now(),
            )
        except McpOAuthGrant.DoesNotExist:
            return None
        return RefreshToken(
            token=raw_token,
            client_id=row.client.client_id,
            scopes=row.scopes,
            expires_at=int(row.refresh_expires_at.timestamp()),
            subject=row.subject,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        return await sync_to_async(self._exchange_refresh_token, thread_sensitive=True)(
            client.client_id, refresh_token, scopes
        )

    @staticmethod
    @transaction.atomic
    def _exchange_refresh_token(
        client_id: str | None, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        try:
            grant = McpOAuthGrant.objects.select_for_update().select_related("client").filter(
                Q(client__expires_at__isnull=True) | Q(client__expires_at__gt=timezone.now())
            ).get(
                client__client_id=client_id,
                client__active=True,
                refresh_token_digest=token_digest(refresh_token.token),
                active=True,
                refresh_expires_at__gt=timezone.now(),
            )
        except McpOAuthGrant.DoesNotExist as exc:
            raise TokenError(error="invalid_grant", error_description="Refresh token is invalid or expired.") from exc
        requested = scopes or grant.scopes
        if set(requested) - set(grant.scopes):
            raise TokenError(error="invalid_scope", error_description="Requested scope exceeds the original grant.")
        grant.active = False
        grant.save(update_fields=["active"])
        return DjangoOAuthProvider._issue_grant(grant.client, requested, grant.subject)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await sync_to_async(self._load_access_token, thread_sensitive=True)(token)

    @staticmethod
    @transaction.atomic
    def _load_access_token(raw_token: str) -> AccessToken | None:
        try:
            row = McpOAuthGrant.objects.select_for_update().select_related("client").filter(
                Q(client__expires_at__isnull=True) | Q(client__expires_at__gt=timezone.now())
            ).get(
                access_token_digest=token_digest(raw_token),
                active=True,
                access_expires_at__gt=timezone.now(),
                client__active=True,
            )
        except McpOAuthGrant.DoesNotExist:
            return None
        now = timezone.now()
        row.last_used_at = now
        row.save(update_fields=["last_used_at"])
        McpOAuthClient.objects.filter(pk=row.client_id).update(last_used_at=now)
        return AccessToken(
            token=raw_token,
            client_id=row.client.client_id,
            scopes=row.scopes,
            expires_at=int(row.access_expires_at.timestamp()),
            resource=None,
            subject=row.subject,
            claims={"iss": "openskagit", "auth_method": "oauth_authorization_code"},
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await sync_to_async(self._revoke_token, thread_sensitive=True)(token.token)

    @staticmethod
    def _revoke_token(raw_token: str) -> None:
        digest = token_digest(raw_token)
        McpOAuthGrant.objects.filter(access_token_digest=digest).update(active=False)
        McpOAuthGrant.objects.filter(refresh_token_digest=digest).update(active=False)

    @staticmethod
    def _issue_grant(client: McpOAuthClient, scopes: list[str], subject: str) -> OAuthToken:
        access_token = "skmcp_at_" + secrets.token_urlsafe(36)
        refresh_token = "skmcp_rt_" + secrets.token_urlsafe(36)
        now = timezone.now()
        McpOAuthGrant.objects.create(
            client=client,
            access_token_digest=token_digest(access_token),
            refresh_token_digest=token_digest(refresh_token),
            scopes=scopes,
            subject=subject,
            access_expires_at=now + timedelta(seconds=ACCESS_TTL_SECONDS),
            refresh_expires_at=now + timedelta(seconds=REFRESH_TTL_SECONDS),
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TTL_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refresh_token,
        )
