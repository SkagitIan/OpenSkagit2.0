from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from .services.importers import infer_street_side, normalize_row, read_upload
from .services.optimization import cluster_and_order


class ImporterTests(TestCase):
    def test_normalizes_state_plane_coordinates_to_wgs84(self):
        row = normalize_row({"PARCELID": "P1", "XCoordinate": "1288931.1465", "YCoordinate": "518163.804", "SitusStName": "ALPINE VIEW PLACE"})
        self.assertEqual(row["parcel_id"], "P1")
        self.assertAlmostEqual(row["longitude"], -122.280654, places=5)
        self.assertAlmostEqual(row["latitude"], 48.411445, places=5)
        self.assertEqual(row["validation_status"], "valid")

    def test_reads_the_provided_xlsx_without_openpyxl(self):
        path = Path(r"C:\Users\ian\Downloads\Export (13).xlsx")
        if not path.exists():
            self.skipTest("sample export is not present")
        upload = SimpleNamespace(name=path.name, read=path.read_bytes)
        headers, rows, file_type = read_upload(upload)
        self.assertEqual(file_type, "xlsx")
        self.assertEqual(len(headers), 70)
        self.assertEqual(len(rows), 310)

    def test_infers_common_odd_even_street_side(self):
        self.assertEqual(infer_street_side("1612"), "even")
        self.assertEqual(infer_street_side("1630 ALPINE VIEW DRIVE"), "even")
        self.assertEqual(infer_street_side("1613"), "odd")


class OptimizationTests(TestCase):
    def test_clusters_are_capacity_bounded(self):
        items = [{"id": i, "parcel_id": str(i), "longitude": -122.35 + (i % 30) * .001, "latitude": 48.42 + (i // 30) * .001, "street_name": "MAIN"} for i in range(291)]
        groups = cluster_and_order(items, target=60)
        self.assertEqual(sum(map(len, groups)), 291)
        self.assertEqual([len(group) for group in groups], [59, 58, 58, 58, 58])
        self.assertTrue(all(50 <= len(group) <= 75 for group in groups))
