from django.test import SimpleTestCase

from parcelbook.ai.prompts import planner_user_prompt
from parcelbook.data.schema_guide import schema_guide


class SchemaGuideTests(SimpleTestCase):
    def test_schema_guide_contains_core_warnings(self):
        text = schema_guide()
        self.assertIn("one row per parcel_number", text)
        self.assertIn("primary_building_living_area", text)
        self.assertIn("has_geometry", text)

    def test_planner_prompt_includes_skill_markdown(self):
        prompt = planner_user_prompt("Find ADU candidates")
        self.assertIn("ParcelBook Query Planner Skill", prompt)
        self.assertIn("Do not invent fields", prompt)
