from django.test import SimpleTestCase

from parcelbook.ai.parcel_query_planner import heuristic_plan
from parcelbook.ai.sql_safety import validate_select_sql

PROMPTS = [
    "Find possible ADU candidates in Mount Vernon.",
    "Show me city parcels with older small homes on larger lots.",
    "Find rural residential parcels between 2 and 10 acres with older homes.",
    "Show me properties that already appear to have a secondary detached unit.",
    "Find parcels in Sedro-Woolley with no recent sale and moderate assessed value.",
]


class QueryPlannerExampleTests(SimpleTestCase):
    def test_example_prompts_generate_safe_select_sql(self):
        for prompt in PROMPTS:
            with self.subTest(prompt=prompt):
                plan = heuristic_plan(prompt)
                safe = validate_select_sql(plan.sql)
                self.assertIn("read_parquet('r2://openskagit/derived/parcel_search.parquet')", safe)
                self.assertIn("LIMIT", safe.upper())
                self.assertIn("match_score", safe)
