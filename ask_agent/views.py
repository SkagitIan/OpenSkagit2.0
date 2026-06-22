import json

from django.http import HttpResponseNotAllowed, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlencode

from core.views import CITY_PAGES


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

    def events():
        if not prompt:
            html = render_to_string("partials/ask_messages.html", {"error": "Please enter a question."})
            yield _sse("answer", {"html": html})
            yield _sse("done", {})
            return

        yield _sse("status", {"message": "thinking"})
        yield _sse("status", {"message": "querying"})
        yield _sse("status", {"message": "summarizing"})

        from .agent import answer_question

        analysis = answer_question(prompt)
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


def ask(request):
    answer = None
    analysis = None
    result = None
    sql = ""
    prompt = ""
    composer_prompt = request.GET.get("prompt", "").strip()
    error = None

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        composer_prompt = ""
        if prompt:
            from .agent import answer_question
            analysis = answer_question(prompt)
            answer = analysis.answer
            result = analysis.result
            sql = analysis.sql or ""

    context = {
        "answer": answer,
        "analysis": analysis,
        "result": result,
        "sql": sql,
        "prompt": prompt,
        "composer_prompt": composer_prompt,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
        "city_pages": CITY_PAGES,
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "partials/ask_messages.html", context)

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
