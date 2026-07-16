from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.utils import timezone

CLAUDE_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
]


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class McpAccessRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_APPROVED, "Approved"), (STATUS_DECLINED, "Declined")]

    name = models.CharField(max_length=120)
    email = models.EmailField(db_index=True)
    organization = models.CharField(max_length=160, blank=True)
    agent_client = models.CharField(max_length=120, blank=True)
    intended_use = models.TextField()
    expected_volume = models.CharField(
        max_length=20,
        choices=[("low", "Occasional"), ("medium", "Regular"), ("high", "High volume")],
        default="low",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    agreed_to_terms = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class McpOAuthClient(models.Model):
    access_request = models.ForeignKey(
        McpAccessRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="oauth_clients"
    )
    name = models.CharField(max_length=160)
    client_id = models.CharField(max_length=100, unique=True, db_index=True)
    encrypted_client_secret = models.TextField()
    redirect_uris = models.JSONField(default=list)
    scope = models.CharField(max_length=200, default="openskagit.read")
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.client_id})"

    @classmethod
    def issue(
        cls,
        *,
        name: str,
        access_request: McpAccessRequest | None = None,
        redirect_uris: list[str] | None = None,
        days: int = 365,
    ) -> tuple["McpOAuthClient", str]:
        raw_secret = "skmcp_client_" + secrets.token_urlsafe(36)
        instance = cls(
            access_request=access_request,
            name=name,
            client_id="skmcp_" + secrets.token_urlsafe(18),
            redirect_uris=redirect_uris or list(CLAUDE_REDIRECT_URIS),
            expires_at=timezone.now() + timedelta(days=days) if days else None,
        )
        instance.set_client_secret(raw_secret)
        instance.save()
        return instance, raw_secret

    def set_client_secret(self, raw_secret: str) -> None:
        self.encrypted_client_secret = _fernet().encrypt(raw_secret.encode("utf-8")).decode("ascii")

    def get_client_secret(self) -> str:
        return _fernet().decrypt(self.encrypted_client_secret.encode("ascii")).decode("utf-8")

    @property
    def is_available(self) -> bool:
        return self.active and (self.expires_at is None or self.expires_at > timezone.now())


class McpOAuthAuthorizationCode(models.Model):
    client = models.ForeignKey(McpOAuthClient, on_delete=models.CASCADE, related_name="authorization_codes")
    code_digest = models.CharField(max_length=64, unique=True, db_index=True)
    scopes = models.JSONField(default=list)
    redirect_uri = models.TextField()
    redirect_uri_provided_explicitly = models.BooleanField(default=True)
    code_challenge = models.CharField(max_length=180)
    subject = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class McpOAuthGrant(models.Model):
    client = models.ForeignKey(McpOAuthClient, on_delete=models.CASCADE, related_name="grants")
    access_token_digest = models.CharField(max_length=64, unique=True, db_index=True)
    refresh_token_digest = models.CharField(max_length=64, unique=True, db_index=True)
    scopes = models.JSONField(default=list)
    subject = models.CharField(max_length=200, blank=True)
    access_expires_at = models.DateTimeField(db_index=True)
    refresh_expires_at = models.DateTimeField(db_index=True)
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class McpToolCall(models.Model):
    """Minimal, secret-free evidence for MCP adoption and reliability."""

    tool_name = models.CharField(max_length=100, db_index=True)
    caller_class = models.CharField(max_length=40, db_index=True)
    outcome = models.CharField(max_length=20, db_index=True)
    duration_ms = models.PositiveIntegerField()
    freshness_status = models.CharField(max_length=20, default="unknown")
    freshness_as_of = models.CharField(max_length=80, blank=True)
    error_class = models.CharField(max_length=120, blank=True)
    called_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-called_at"]
        indexes = [models.Index(fields=["tool_name", "called_at"], name="mcp_tool_time_idx")]
