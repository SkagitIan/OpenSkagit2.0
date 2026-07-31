from django.test import SimpleTestCase

from ask_agent.agent import is_safe_analysis_sql, is_safe_select


class AskAgentPublicSqlSafetyTests(SimpleTestCase):
    def test_allows_declared_public_analysis_table(self):
        self.assertTrue(is_safe_select("SELECT parcel_number FROM assessor_rollup LIMIT 5"))

    def test_allows_cte_over_public_table(self):
        self.assertTrue(is_safe_select("WITH recent AS (SELECT * FROM sales) SELECT * FROM recent"))

    def test_rejects_unlisted_django_and_budget_workflow_tables(self):
        self.assertFalse(is_safe_select("SELECT * FROM auth_user"))
        self.assertFalse(is_safe_select("SELECT * FROM budgets_budgetdocument"))

    def test_temp_analysis_must_read_only_public_tables(self):
        self.assertTrue(is_safe_analysis_sql("CREATE TEMP TABLE analysis_sales AS SELECT * FROM sales"))
        self.assertFalse(is_safe_analysis_sql("CREATE TEMP TABLE analysis_users AS SELECT * FROM auth_user"))