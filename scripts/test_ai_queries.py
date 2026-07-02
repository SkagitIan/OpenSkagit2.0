#!/usr/bin/env python
import json
from pathlib import Path

from parcelbook.ai.ask import ask_parcels

PROMPTS = [
    "Find possible ADU candidates in Mount Vernon.",
    "Show me city parcels with older small homes on larger lots.",
    "Find rural residential parcels between 2 and 10 acres with older homes.",
    "Show me properties that already appear to have a secondary detached unit.",
    "Find parcels in Sedro-Woolley with no recent sale and moderate assessed value.",
    "Find recently sold residential parcels on larger lots.",
    "Find large lot small house opportunities.",
    "Show me manufactured homes on large parcels under $400k assessed value.",
    "Find parcels with no situs address but valid geometry.",
    "Find residential parcels with missing geometry.",
]

if __name__ == "__main__":
    out = []
    for prompt in PROMPTS:
        result = ask_parcels(prompt)
        out.append({
            "query": prompt,
            "generated_sql": result["sql"],
            "row_count": result["row_count"],
            "sample_results": result["results"][:5],
            "passed_basic_sanity_checks": result["row_count"] >= 0 and "LIMIT" in result["sql"].upper(),
        })
    Path("parcelbook_ai_query_eval.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
