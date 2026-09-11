from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import PreinspectionWorkspace
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


class PreinspectionWorkspaceTests(TestCase):
    def test_aerial_notes_are_saved_on_input_and_before_modal_close(self):
        template = (Path(__file__).parent / "templates" / "routing" / "preinspection_workspace.html").read_text(encoding="utf-8")
        self.assertIn("function saveInspectionNotes(pid,value)", template)
        self.assertIn('if(notesInput) saveInspectionNotes(pid,notesInput.value);', template)
        self.assertIn('["input","change","blur"]', template)

    def test_sketch_button_uses_a_leaflet_map_not_the_click_event(self):
        template = (Path(__file__).parent / "templates" / "routing" / "preinspection_workspace.html").read_text(encoding="utf-8")
        self.assertIn("let activeSketchMap=current;", template)
        self.assertIn("if(!(targetMap instanceof L.Map)) targetMap=activeSketchMap || current;", template)
        self.assertIn('sketchButton.addEventListener("click",()=>toggleSketch(activeSketchMap || current));', template)
        self.assertNotIn('sketchButton.addEventListener("click",toggleSketch);', template)

    def test_preinspection_tracks_and_advances_active_parcel(self):
        template = (Path(__file__).parent / "templates" / "routing" / "preinspection_workspace.html").read_text(encoding="utf-8")
        self.assertIn('if(!Object.prototype.hasOwnProperty.call(state,"activeParcel")) state.activeParcel="";', template)
        self.assertIn("function advanceActiveParcelFrom(pid)", template)
        self.assertIn('if(shouldAdvance) advanceActiveParcelFrom(pid);', template)
        self.assertIn('tr.classList.add("active-parcel");', template)
        self.assertIn('row.scrollIntoView({behavior:"smooth",block:"center"});', template)
        self.assertIn(".preinspection-table tbody tr.complete:not(.active-parcel){opacity:.45}", template)

    def test_field_routes_keep_appraisal_routes_and_support_ordered_copy(self):
        template = (Path(__file__).parent / "templates" / "routing" / "preinspection_workspace.html").read_text(encoding="utf-8")
        self.assertIn('data-view="fieldRoutes"', template)
        self.assertIn('state.fieldRoutes={};', template)
        self.assertIn('function addYesParcelToFieldRoute(pid)', template)
        self.assertIn('if(next==="yes") addYesParcelToFieldRoute(pid);', template)
        self.assertIn('function moveFieldParcel(pid,targetRoute,insertIndex=null)', template)
        self.assertIn('const text=values.join("\\n");', template)
        self.assertIn('String(pid).replace(/^P/i,"")', template)
        self.assertIn('id="fieldRouteMap"', template)
        self.assertIn('data-field-pid', template)
        self.assertIn('data-field-route-drop', template)
        self.assertIn('const targetRoute=stop?.dataset.fieldRoute || drop?.dataset.fieldRouteDrop;', template)

    def test_field_route_map_renders_only_selected_route_and_legacy_yes_parcels_seed(self):
        template = (Path(__file__).parent / "templates" / "routing" / "preinspection_workspace.html").read_text(encoding="utf-8")
        self.assertIn('const route=state.fieldRoutes[routeName];', template)
        self.assertIn('(route?.parcels||[]).forEach((pid,index)=>', template)
        self.assertIn('const legacyYes=state.assignment.map(a=>a.PARCELID).filter(pid=>inspection(pid).changes==="yes");', template)
        self.assertIn('state.fieldRoutes[legacyRoute].parcels=[...new Set(legacyYes)];', template)


class WorkspaceApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice", password="test-password")
        self.bob = User.objects.create_user(username="bob", password="test-password")
        self.admin = User.objects.create_superuser(username="admin", password="test-password", email="admin@example.com")
        self.state = {
            "version": 2,
            "year": 2026,
            "assignment": [{"PARCELID": "P123"}],
            "parcelGeoJSON": None,
            "routes": {},
            "inspections": {"P123": {"changes": "yes", "notes": "field visit"}},
            "fieldRoutes": {"Field Route 1": {"parcels": ["P123"]}},
            "fieldUnassigned": [],
            "activeParcel": "P123",
            "activeFieldRoute": "Field Route 1",
        }

    def test_authenticated_users_can_create_and_reload_private_workspaces(self):
        client = Client()
        self.assertEqual(client.get("/routing/").status_code, 302)
        self.assertTrue(client.login(username="alice", password="test-password"))
        self.assertEqual(client.get("/routing/").status_code, 200)
        created = client.post("/routing/api/workspaces/", data={"name": "Alice 2026", "state": self.state}, content_type="application/json")
        self.assertEqual(created.status_code, 201)
        workspace_id = created.json()["id"]
        loaded = client.get(f"/routing/api/workspaces/{workspace_id}/")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["state"]["fieldRoutes"]["Field Route 1"]["parcels"], ["P123"])

    def test_workspace_records_are_isolated_between_users(self):
        owner_client = Client()
        self.assertTrue(owner_client.login(username="alice", password="test-password"))
        created = owner_client.post("/routing/api/workspaces/", data={"name": "Private", "state": self.state}, content_type="application/json")
        workspace_id = created.json()["id"]

        other_client = Client()
        self.assertTrue(other_client.login(username="bob", password="test-password"))
        self.assertEqual(other_client.get("/routing/api/workspaces/").json()["workspaces"], [])
        self.assertEqual(other_client.get(f"/routing/api/workspaces/{workspace_id}/").status_code, 404)
        self.assertEqual(other_client.put(f"/routing/api/workspaces/{workspace_id}/state/", data={"revision": 1, "state": self.state}, content_type="application/json").status_code, 404)

    def test_revision_conflict_does_not_overwrite_newer_workspace_state(self):
        client = Client()
        self.assertTrue(client.login(username="alice", password="test-password"))
        created = client.post("/routing/api/workspaces/", data={"name": "Revision test", "state": self.state}, content_type="application/json").json()
        changed = {**self.state, "activeParcel": "P999"}
        first = client.put(f"/routing/api/workspaces/{created['id']}/state/", data={"revision": created["revision"], "state": changed}, content_type="application/json")
        self.assertEqual(first.status_code, 200)
        stale = client.put(f"/routing/api/workspaces/{created['id']}/state/", data={"revision": created["revision"], "state": self.state}, content_type="application/json")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(PreinspectionWorkspace.objects.get(pk=created["id"]).state["activeParcel"], "P999")

    def test_superuser_can_list_other_users_workspaces(self):
        owner_client = Client()
        self.assertTrue(owner_client.login(username="alice", password="test-password"))
        owner_client.post("/routing/api/workspaces/", data={"name": "Visible to admin", "state": self.state}, content_type="application/json")
        admin_client = Client()
        self.assertTrue(admin_client.login(username="admin", password="test-password"))
        payload = admin_client.get("/routing/api/workspaces/").json()
        self.assertEqual(len(payload["workspaces"]), 1)
