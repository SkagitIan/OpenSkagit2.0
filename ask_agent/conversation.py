from __future__ import annotations

from django.core.exceptions import ValidationError

from .agent import AnalysisResponse
from .models import AskMessage, AskThread


def get_thread(thread_id) -> AskThread | None:
    if not thread_id:
        return None
    try:
        return AskThread.objects.prefetch_related("messages").get(pk=thread_id)
    except (AskThread.DoesNotExist, ValueError, TypeError, ValidationError):
        return None


def create_thread(first_prompt: str) -> AskThread:
    return AskThread.objects.create(title=first_prompt.strip()[:200])


def append_user_message(thread: AskThread, content: str) -> AskMessage:
    return AskMessage.objects.create(thread=thread, role=AskMessage.Role.USER, content=content)


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def append_assistant_message(thread: AskThread, analysis: AnalysisResponse) -> AskMessage:
    structured_result = {}
    if analysis.result is not None:
        structured_result = _json_safe({"columns": analysis.result.columns, "rows": analysis.result.rows})
    message = AskMessage.objects.create(
        thread=thread,
        role=AskMessage.Role.ASSISTANT,
        content=analysis.answer,
        sql=analysis.sql or "",
        structured_result=structured_result,
        response_id=analysis.response_id or "",
    )
    if analysis.response_id:
        thread.last_response_id = analysis.response_id
        thread.save(update_fields=["last_response_id", "updated_at"])
    return message
