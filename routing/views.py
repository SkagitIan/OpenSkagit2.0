import json

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import RoutingImport, RoutingImportRow, RoutingPlan, RoutingRoute, RoutingStop
from .services.exports import route_csv
from .services.importers import normalize_row, read_upload
from .services.optimization import cluster_and_order, distance
from .services.matrices import travel_matrix


def _staff(request):
    return bool(request.user.is_authenticated and request.user.is_active and request.user.is_staff)


def _forbidden(request):
    return redirect_to_login(request.get_full_path(), "/login/")


@require_GET
def routes_page(request):
    if not _staff(request):
        return _forbidden(request)
    return render(request, "routing/routes.html", {"imports": RoutingImport.objects.all()[:20]})


@require_http_methods(["POST"])
def import_file(request):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": "Choose a CSV or XLSX file."}, status=400)
    try:
        headers, source_rows, file_type = read_upload(upload)
        normalized = [normalize_row(row) for row in source_rows]
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    unique = {}
    for row in normalized:
        key = (row["parcel_id"], row["longitude"], row["latitude"])
        if row["parcel_id"] and row["longitude"] is not None and key not in unique:
            unique[key] = row
    summary = {
        "blank_rows": sum(not row["parcel_id"] and row["longitude"] is None for row in normalized),
        "duplicate_rows": max(0, sum(bool(row["parcel_id"]) for row in normalized) - len(unique)),
        "missing_coordinates": sum("missing_coordinates" in row["validation_notes"] for row in normalized),
        "addressless_rows": sum(not row["address"] for row in normalized),
    }
    import_file_obj = RoutingImport.objects.create(
        filename=upload.name, file_type=file_type, row_count=len(normalized),
        unique_stop_count=len(unique), original_headers=headers, summary=summary,
    )
    RoutingImportRow.objects.bulk_create([
        RoutingImportRow(
            import_file=import_file_obj, source_row_number=index, parcel_id=row["parcel_id"],
            address=row["address"], source_x=row["source_x"], source_y=row["source_y"],
            longitude=row["longitude"], latitude=row["latitude"],
            point_geometry={"type": "Point", "coordinates": [row["longitude"], row["latitude"]]} if row["longitude"] is not None else None,
            source_data=row["source_data"], validation_status=row["validation_status"],
            validation_notes=row["validation_notes"], dedupe_key="|".join(map(str, (row["parcel_id"], row["longitude"], row["latitude"]))),
        ) for index, row in enumerate(normalized, start=2)
    ])
    return JsonResponse({"import_id": import_file_obj.id, "filename": upload.name, "row_count": len(normalized), "unique_stop_count": len(unique), "summary": summary})


def _plan_payload(plan):
    routes = []
    for route in plan.routes.prefetch_related("stops__import_row"):
        stops = [{"sequence": stop.sequence, "parcel_id": stop.parcel_id, "address": stop.import_row.address, "longitude": stop.longitude, "latitude": stop.latitude, "street_name": stop.street_name, "street_side": stop.street_side, "confidence": stop.coordinate_confidence} for stop in route.stops.all()]
        routes.append({"route_number": route.route_number, "stop_count": route.stop_count, "stops": stops})
    return {"plan_id": plan.id, "mode": plan.mode, "target_stop_count": plan.target_stop_count, "route_count": plan.route_count, "summary": plan.summary, "routes": routes}


@require_http_methods(["POST"])
def create_plan(request):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    try:
        body = json.loads(request.body or "{}")
        import_obj = get_object_or_404(RoutingImport, pk=int(body["import_id"]))
        mode = body.get("mode", "driving")
        target = max(50, min(75, int(body.get("target_stop_count", 60))))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "A valid import_id and target_stop_count are required."}, status=400)
    raw_items = list(import_obj.rows.filter(validation_status="valid").values("id", "parcel_id", "address", "longitude", "latitude", "source_data"))
    items_by_key = {}
    for item in raw_items:
        items_by_key.setdefault((item["parcel_id"], item["longitude"], item["latitude"]), item)
    items = list(items_by_key.values())
    for item in items:
        source = item.get("source_data") or {}
        item["street_name"] = str(source.get("SitusStName") or source.get("street_name") or "").strip()
    groups = cluster_and_order(items, target=target, mode=mode)
    plan = RoutingPlan.objects.create(import_file=import_obj, mode=mode, target_stop_count=target, route_count=len(groups), status="clustered", algorithm_version="cluster-v1", summary={"valid_stops": len(items), "unassigned_stops": import_obj.rows.exclude(validation_status="valid").count()})
    for route_number, group in enumerate(groups, start=1):
        total = sum(distance((a["longitude"], a["latitude"]), (b["longitude"], b["latitude"])) for a, b in zip(group, group[1:]))
        route = RoutingRoute.objects.create(plan=plan, route_number=route_number, stop_count=len(group), estimated_distance_meters=total)
        RoutingStop.objects.bulk_create([RoutingStop(route=route, import_row_id=item["id"], sequence=sequence, parcel_id=item["parcel_id"], longitude=item["longitude"], latitude=item["latitude"], street_name=item.get("street_name", ""), coordinate_confidence="source_xy") for sequence, item in enumerate(group, start=1)])
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def optimize_plan(request, plan_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    for route in plan.routes.prefetch_related("stops"):
        stops = list(route.stops.all())
        items = [{"id": stop.id, "parcel_id": stop.parcel_id, "longitude": stop.longitude, "latitude": stop.latitude, "street_name": stop.street_name} for stop in stops]
        ordered = cluster_and_order(items, target=max(50, len(items)), mode=plan.mode, matrix_factory=travel_matrix)[0] if items else []
        for sequence, item in enumerate(ordered, start=1):
            RoutingStop.objects.filter(pk=item["id"]).update(sequence=sequence, manually_locked=False)
    plan.status = "optimized"
    plan.algorithm_version = "valhalla-matrix-v1"
    plan.save(update_fields=["status", "algorithm_version"])
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def move_stop(request, plan_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    try:
        body = json.loads(request.body or "{}")
        stop = get_object_or_404(RoutingStop, pk=int(body["stop_id"]), route__plan=plan)
        target_route = get_object_or_404(RoutingRoute, pk=int(body["target_route"]), plan=plan)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "A valid stop_id and target_route are required."}, status=400)
    stop.route = target_route
    stop.manually_locked = True
    stop.sequence = target_route.stops.count() + 1
    stop.save(update_fields=["route", "manually_locked", "sequence"])
    plan.status = "clustered"
    plan.save(update_fields=["status"])
    return JsonResponse(_plan_payload(plan))


@require_GET
def plan_detail(request, plan_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    return JsonResponse(_plan_payload(get_object_or_404(RoutingPlan, pk=plan_id)))


@require_GET
def export_plan(request, plan_id):
    if not _staff(request):
        return HttpResponse("Staff sign-in is required.", status=403)
    response = HttpResponse(route_csv(get_object_or_404(RoutingPlan, pk=plan_id)), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="route-plan-{plan_id}.csv"'
    return response
