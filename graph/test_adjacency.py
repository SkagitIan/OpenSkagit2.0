from __future__ import annotations
import geopandas as gpd
from django.test import SimpleTestCase
from shapely.geometry import Polygon
from graph.adjacency import build_adjacency

class AdjacencyTests(SimpleTestCase):
    def test_squares_sharing_edge_are_adjacent(self):
        frame = gpd.GeoDataFrame({"parcel_number": ["P1", "P2"]}, geometry=[Polygon([(0,0),(10,0),(10,10),(0,10)]), Polygon([(10,0),(20,0),(20,10),(10,10)])], crs="EPSG:2926")
        result = build_adjacency(frame)
        self.assertEqual(result[["pid_a", "pid_b"]].values.tolist(), [["P1", "P2"]])
        self.assertAlmostEqual(result.iloc[0].shared_boundary_ft, 10.0)
    def test_corner_touch_is_not_adjacent(self):
        frame = gpd.GeoDataFrame({"PARCELID": ["P1", "P2"]}, geometry=[Polygon([(0,0),(10,0),(10,10),(0,10)]), Polygon([(10,10),(20,10),(20,20),(10,20)])], crs="EPSG:2926")
        self.assertTrue(build_adjacency(frame).empty)
    def test_disjoint_is_not_adjacent(self):
        frame = gpd.GeoDataFrame({"parcel_number": ["P1", "P2"]}, geometry=[Polygon([(0,0),(1,0),(1,1),(0,1)]), Polygon([(5,5),(6,5),(6,6),(5,6)])], crs="EPSG:2926")
        self.assertTrue(build_adjacency(frame).empty)
    def test_invalid_geometry_is_repaired_and_counted(self):
        bowtie = Polygon([(0,0),(10,10),(0,10),(10,0),(0,0)])
        frame = gpd.GeoDataFrame({"parcel_number": ["P1"]}, geometry=[bowtie], crs="EPSG:2926")
        result = build_adjacency(frame)
        self.assertEqual(result.attrs["invalid_repaired"], 1)