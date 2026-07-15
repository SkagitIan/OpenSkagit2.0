from unittest.mock import patch

from django.test import SimpleTestCase

from opportunity import services


class AssemblageTabTests(SimpleTestCase):
    def test_assemblage_tab_is_registered(self):
        self.assertIn("assemblage-opportunities", {tab.key for tab in services.TABS})
        self.assertEqual(services.TAB_LOOKUP["assemblage-opportunities"].label, "Parcel Assemblages")

    @patch("opportunity.services.assemblage_opportunities", return_value=[{"parcel_number": "P1"}])
    def test_assemblage_tab_dispatches_to_graph_backed_service(self, assemblage):
        rows = services.fetch_tab_rows("assemblage-opportunities", {}, limit=1)
        self.assertEqual(rows, [{"parcel_number": "P1"}])
        assemblage.assert_called_once_with({}, 5)