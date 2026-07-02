from django.test import SimpleTestCase

from parcelbook.ai.sql_safety import validate_select_sql


class SqlSafetyTests(SimpleTestCase):
    def test_adds_limit_to_allowed_select(self):
        sql = "SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')"
        safe = validate_select_sql(sql, limit=7)
        self.assertIn("LIMIT 7", safe)

    def test_rejects_destructive_sql(self):
        with self.assertRaises(ValueError):
            validate_select_sql("DROP TABLE parcels")

    def test_rejects_wrong_source(self):
        with self.assertRaises(ValueError):
            validate_select_sql("SELECT * FROM read_parquet('r2://openskagit/sales.parquet') LIMIT 5")
