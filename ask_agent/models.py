from __future__ import annotations

import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AskThread(models.Model):
    """A persisted /ask conversation. UUID primary key so a thread is a shareable,
    bookmarkable permalink (/ask/t/<uuid>/) without requiring a user account --
    this site has no citizen login."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, blank=True)
    last_response_id = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or str(self.id)


class AskMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    thread = models.ForeignKey(AskThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField(blank=True)
    sql = models.TextField(blank=True)
    structured_result = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    response_id = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.thread_id} {self.role}: {self.content[:60]}"
