from django.shortcuts import render
from django.http import HttpResponseNotAllowed

STARTER_PROMPTS = [
    "How many parcels are in each city?",
    "What are the largest parcels by acreage in Mount Vernon?",
    "Show recent sales by neighborhood with median price",
    "Which land use codes are most common?",
    "Parcels over 10 acres with public utilities",
    "IAAO sales ratio check for residential properties",
]


def home(request):
    return render(request, "pages/home.html")


def app(request):
    return render(request, "pages/app.html")


def ask(request):
    answer = None
    analysis = None
    result = None
    sql = ""
    prompt = request.GET.get("prompt", "").strip()
    error = None

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        if prompt:
            from .agent import answer_question
            analysis = answer_question(prompt)
            answer = analysis.answer
            result = analysis.result
            sql = analysis.sql or ""

    return render(request, "pages/ask.html", {
        "answer": answer,
        "analysis": analysis,
        "result": result,
        "sql": sql,
        "prompt": prompt,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
    })


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
    })
