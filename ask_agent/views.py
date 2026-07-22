import json

from django.http import Http404, HttpResponseNotAllowed, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlencode

from core.views import CITY_PAGES

from . import conversation


STARTER_PROMPTS = [
    "How many parcels are in each city?",
    "What are the largest parcels by acreage in Mount Vernon?",
    "Show recent sales by neighborhood with median price",
    "Which land use codes are most common?",
    "Parcels over 10 acres with public utilities",
    "IAAO sales ratio check for residential properties",
]


def app(request):
    prompt = request.GET.get("prompt", request.GET.get("q", "")).strip()
    url = reverse("ask")
    if prompt:
        url = f"{url}?{urlencode({'prompt': prompt})}"
    return redirect(url)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def ask_stream(request):
    prompt = request.GET.get("prompt", "").strip()
    thread_id = request.GET.get("thread", "").strip()

    def events():
        if not prompt:
            html = render_to_string("partials/ask_messages.html", {"error": "Please enter a question."})
            yield _sse("answer", {"html": html})
            yield _sse("done", {})
            return

        thread = conversation.get_thread(thread_id) if thread_id else None
        is_new_thread = thread is None
        if is_new_thread:
            thread = conversation.create_thread(prompt)
        yield _sse("thread", {"id": str(thread.id), "url": reverse("ask_thread", args=[thread.id])})
        conversation.append_user_message(thread, prompt)

        from .agent import AnalysisResponse, QueryResult, stream_ask_turn

        final_event = {"answer": "Analysis is temporarily unavailable.", "response_id": None}
        for event in stream_ask_turn(prompt, thread.last_response_id or None):
            if event["type"] == "status":
                yield _sse("status", {"message": event["message"]})
            elif event["type"] == "heartbeat":
                yield _sse("heartbeat", {})
            elif event["type"] == "final":
                final_event = event

        result_payload = final_event.get("result")
        result = QueryResult(**result_payload) if result_payload else None
        analysis = AnalysisResponse(
            answer=final_event.get("answer", ""),
            result=result,
            sql=final_event.get("sql") or None,
            response_id=final_event.get("response_id"),
        )
        conversation.append_assistant_message(thread, analysis)
        html = render_to_string("partials/ask_messages.html", {
            "answer": analysis.answer,
            "analysis": analysis,
            "result": analysis.result,
            "sql": analysis.sql or "",
        })
        yield _sse("answer", {"html": html})
        yield _sse("done", {})

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def ask(request, thread_id=None):
    thread = None
    if thread_id is not None:
        thread = conversation.get_thread(thread_id)
        if thread is None:
            raise Http404("No such conversation.")

    composer_prompt = request.GET.get("prompt", "").strip() if thread is None else ""
    error = None

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        if prompt:
            from .agent import answer_question

            if thread is None:
                thread = conversation.create_thread(prompt)
            conversation.append_user_message(thread, prompt)
            analysis = answer_question(prompt, thread.last_response_id or None)
            conversation.append_assistant_message(thread, analysis)
            # Post-redirect-get: avoids resubmitting the question on refresh, and gives
            # the conversation a stable, bookmarkable URL even without JavaScript.
            return redirect("ask_thread", thread_id=thread.id)
        error = "Please enter a question."

    context = {
        "thread": thread,
        "thread_messages": list(thread.messages.all()) if thread is not None else [],
        "composer_prompt": composer_prompt,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
        "city_pages": CITY_PAGES,
    }
    return render(request, "pages/ask.html", context)


def ask_sql(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    sql = request.POST.get("sql", "").strip()
    prompt = request.POST.get("prompt", "").strip()
    result = None
    error = None

    if sql:
        from .agent import execute_analysis_sql
        try:
            result = execute_analysis_sql(sql)
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

    return render(request, "pages/ask.html", {
        "sql": sql,
        "prompt": prompt,
        "result": result,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
        "city_pages": CITY_PAGES,
    })
