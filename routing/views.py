import json

from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import RoutingImport, RoutingImportRow, RoutingPlan, RoutingPlanRevision, RoutingRoute, RoutingStop
from .services.exports import route_csv, single_route_csv
from .services.importers import infer_street_side, normalize_row, read_upload
from .services.optimization import cluster_and_order, distance
from .services.matrices import travel_matrix
from .services.valhalla import optimized_order


def _staff(request):
    return bool(request.user.is_authenticated and request.user.is_active and request.user.is_staff)


def _forbidden(request):
    return redirect_to_login(request.get_full_path(), "/login/")


@require_GET
def routes_page(request):
    if not _staff(request):
        return _forbidden(request)
    return render(request, "routing/routes.html", {"imports": RoutingImport.objects.all()[:20], "plans": RoutingPlan.objects.select_related("import_file")[:30]})


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
        stops = [{"id": stop.id, "import_row_id": stop.import_row_id, "sequence": stop.sequence, "parcel_id": stop.parcel_id, "address": stop.import_row.address, "longitude": stop.longitude, "latitude": stop.latitude, "street_name": stop.street_name, "street_side": stop.street_side, "confidence": stop.coordinate_confidence} for stop in route.stops.all()]
        routes.append({"id": route.id, "route_number": route.route_number, "mode": route.mode, "stop_count": route.stop_count, "geometry": route.geometry, "stops": stops})
    latest_revision = plan.revisions.first()
    assigned_ids = [stop["id"] for route in routes for stop in route["stops"]]
    return {"plan_id": plan.id, "name": plan.name, "import_id": plan.import_file_id, "status": plan.status, "revision": latest_revision.revision_number if latest_revision else 0, "mode": plan.mode, "target_stop_count": plan.target_stop_count, "route_count": plan.route_count, "summary": plan.summary, "routes": routes, "assigned_stop_ids": assigned_ids}


def _record_revision(plan, action):
    next_number = (plan.revisions.order_by("-revision_number").values_list("revision_number", flat=True).first() or 0) + 1
    RoutingPlanRevision.objects.create(plan=plan, revision_number=next_number, action=action, snapshot=_plan_payload(plan))


@require_GET
def plans_list(request):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    return JsonResponse({"plans": [{"id": plan.id, "name": plan.name, "filename": plan.import_file.filename, "mode": plan.mode, "status": plan.status, "route_count": plan.route_count, "created_at": plan.created_at.isoformat()} for plan in RoutingPlan.objects.select_related("import_file")[:30]]})


@require_http_methods(["POST"])
def create_plan(request):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    try:
        body = json.loads(request.body or "{}")
        import_obj = get_object_or_404(RoutingImport, pk=int(body["import_id"]))
        mode = body.get("mode", "driving")
        target = max(50, min(75, int(body.get("target_stop_count", 60))))
        name = str(body.get("name") or "").strip()[:160]
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
        item["street_side"] = str(source.get("street_side") or infer_street_side(source.get("SitusStNo") or source.get("street_number") or source.get("address"))).strip().lower()
    groups = cluster_and_order(items, target=target, mode=mode)
    plan = RoutingPlan.objects.create(name=name or f"{mode.title()} clusters · {import_obj.filename}", import_file=import_obj, mode=mode, target_stop_count=target, route_count=len(groups), status="clustered", algorithm_version="cluster-v1", summary={"valid_stops": len(items), "unassigned_stops": import_obj.rows.exclude(validation_status="valid").count()})
    for route_number, group in enumerate(groups, start=1):
        total = sum(distance((a["longitude"], a["latitude"]), (b["longitude"], b["latitude"])) for a, b in zip(group, group[1:]))
        route = RoutingRoute.objects.create(plan=plan, route_number=route_number, mode=mode, stop_count=len(group), estimated_distance_meters=total)
        RoutingStop.objects.bulk_create([RoutingStop(route=route, import_row_id=item["id"], sequence=sequence, parcel_id=item["parcel_id"], longitude=item["longitude"], latitude=item["latitude"], street_name=item.get("street_name", ""), street_side=item.get("street_side", ""), coordinate_confidence="source_xy") for sequence, item in enumerate(group, start=1)])
    _record_revision(plan, "clustered")
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def optimize_plan(request, plan_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    for route in plan.routes.prefetch_related("stops"):
        _optimize_route(route, plan)
    plan.status = "optimized"
    plan.algorithm_version = "valhalla-optimized-route-v1"
    plan.save(update_fields=["status", "algorithm_version"])
    _record_revision(plan, "optimized")
    return JsonResponse(_plan_payload(plan))


def _optimize_route(route, plan):
    stops = list(route.stops.all())
    items = [{"id": stop.id, "parcel_id": stop.parcel_id, "longitude": stop.longitude, "latitude": stop.latitude, "street_name": stop.street_name, "street_side": stop.street_side} for stop in stops]
    ordered = items
    shapes = []
    if items:
        try:
            indexes, shapes = optimized_order(items, route.mode)
            if indexes:
                ordered = [items[index] for index in indexes]
        except Exception:
            ordered = cluster_and_order(items, target=max(50, len(items)), mode=route.mode)[0]
            shapes = []
    for sequence, item in enumerate(ordered, start=1):
        RoutingStop.objects.filter(pk=item["id"]).update(sequence=sequence)
    route.geometry = {"encoded_polylines": shapes} if shapes else None
    route.save(update_fields=["geometry"])


def _set_route_order(route, stop_ids):
    stops = {stop.id: stop for stop in route.stops.all()}
    ordered = [stops[stop_id] for stop_id in stop_ids if stop_id in stops]
    ordered += [stop for stop in stops.values() if stop not in ordered]
    for offset, stop in enumerate(ordered, start=1):
        RoutingStop.objects.filter(pk=stop.id).update(sequence=offset + 10000)
    for sequence, stop in enumerate(ordered, start=1):
        RoutingStop.objects.filter(pk=stop.id).update(sequence=sequence)
    route.geometry = None
    route.save(update_fields=["geometry"])


def _renumber_route(route):
    stops = list(route.stops.order_by("sequence", "id"))
    for offset, stop in enumerate(stops, start=1):
        RoutingStop.objects.filter(pk=stop.pk).update(sequence=10000 + offset)
    for sequence, stop in enumerate(stops, start=1):
        RoutingStop.objects.filter(pk=stop.pk).update(sequence=sequence)


@require_http_methods(["POST"])
def optimize_route(request, plan_id, route_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    route = get_object_or_404(RoutingRoute, pk=route_id, plan=plan)
    _optimize_route(route, plan)
    plan.status = "optimized"
    plan.algorithm_version = "valhalla-optimized-route-v1"
    plan.save(update_fields=["status", "algorithm_version"])
    _record_revision(plan, "route_optimized")
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def set_route_mode(request, plan_id, route_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    route = get_object_or_404(RoutingRoute, pk=route_id, plan=plan)
    try:
        mode = json.loads(request.body or "{}").get("mode")
    except json.JSONDecodeError:
        mode = None
    if mode not in {"driving", "walking"}:
        return JsonResponse({"error": "Mode must be driving or walking."}, status=400)
    if route.mode != mode:
        route.mode = mode
        route.geometry = None
        route.save(update_fields=["mode", "geometry"])
        plan.status = "clustered"
        plan.save(update_fields=["status"])
        _record_revision(plan, "route_mode_changed")
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def reverse_route(request, plan_id, route_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    route = get_object_or_404(RoutingRoute, pk=route_id, plan=plan)
    _set_route_order(route, [stop.id for stop in reversed(list(route.stops.all()))])
    plan.status = "clustered"
    plan.save(update_fields=["status"])
    _record_revision(plan, "route_reversed")
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def reset_route(request, plan_id, route_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    route = get_object_or_404(RoutingRoute, pk=route_id, plan=plan)
    first_revision = plan.revisions.order_by("revision_number").first()
    original = next((item for item in (first_revision.snapshot.get("routes", []) if first_revision else []) if item.get("id") == route.id), None)
    if not original:
        return JsonResponse({"error": "The original clustered order could not be found."}, status=409)
    _set_route_order(route, [stop["id"] for stop in original.get("stops", [])])
    plan.status = "clustered"
    plan.save(update_fields=["status"])
    _record_revision(plan, "route_reset")
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
    if stop.route_id == target_route.id:
        return JsonResponse(_plan_payload(plan))
    if target_route.stops.count() >= plan.target_stop_count:
        return JsonResponse({"error": f"Route {target_route.route_number} is already at the {plan.target_stop_count}-stop target."}, status=400)
    source_route = stop.route
    with transaction.atomic():
        stop.route = target_route
        stop.sequence = 100000
        stop.save(update_fields=["route", "sequence"])
        _renumber_route(source_route)
        _renumber_route(target_route)
    source_route.stop_count = source_route.stops.count()
    source_route.geometry = None
    source_route.save(update_fields=["stop_count", "geometry"])
    target_route.stop_count = target_route.stops.count()
    target_route.geometry = None
    target_route.save(update_fields=["stop_count", "geometry"])
    plan.status = "clustered"
    plan.save(update_fields=["status"])
    _record_revision(plan, "stop_moved")
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def remove_stop(request, plan_id, stop_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    stop = get_object_or_404(RoutingStop, pk=stop_id, route__plan=plan)
    route = stop.route
    stop.delete()
    route.stop_count = route.stops.count()
    route.geometry = None
    route.save(update_fields=["stop_count", "geometry"])
    plan.status = "clustered"
    plan.save(update_fields=["status"])
    _record_revision(plan, "stop_removed")
    return JsonResponse(_plan_payload(plan))


@require_http_methods(["POST"])
def add_stop(request, plan_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    try:
        body = json.loads(request.body or "{}")
        row = get_object_or_404(RoutingImportRow, pk=int(body["import_row_id"]), import_file=plan.import_file, validation_status="valid")
        route = get_object_or_404(RoutingRoute, pk=int(body["target_route"]), plan=plan)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "A valid import_row_id and target_route are required."}, status=400)
    if RoutingStop.objects.filter(route__plan=plan, import_row=row).exists():
        return JsonResponse({"error": "That stop is already assigned to this plan."}, status=400)
    if route.stops.count() >= plan.target_stop_count:
        return JsonResponse({"error": f"Route {route.route_number} is already at the {plan.target_stop_count}-stop target."}, status=400)
    source = row.source_data or {}
    stop = RoutingStop.objects.create(route=route, import_row=row, sequence=route.stops.count() + 1, parcel_id=row.parcel_id, longitude=row.longitude, latitude=row.latitude, street_name=str(source.get("SitusStName") or source.get("street_name") or "").strip(), street_side=infer_street_side(source.get("SitusStNo") or source.get("street_number") or source.get("address")), coordinate_confidence="source_xy")
    route.stop_count = route.stops.count()
    route.geometry = None
    route.save(update_fields=["stop_count", "geometry"])
    plan.status = "clustered"
    plan.save(update_fields=["status"])
    _record_revision(plan, "stop_added")
    return JsonResponse(_plan_payload(plan))


@require_GET
def available_stops(request, plan_id):
    if not _staff(request):
        return JsonResponse({"error": "Staff sign-in is required."}, status=403)
    plan = get_object_or_404(RoutingPlan, pk=plan_id)
    assigned = RoutingStop.objects.filter(route__plan=plan).values("import_row_id")
    rows = plan.import_file.rows.filter(validation_status="valid").exclude(id__in=assigned).order_by("parcel_id")[:1000]
    return JsonResponse({"stops": [{"id": row.id, "parcel_id": row.parcel_id, "address": row.address} for row in rows]})


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


@require_GET
def export_route(request, plan_id, route_id):
    if not _staff(request):
        return HttpResponse("Staff sign-in is required.", status=403)
    route = get_object_or_404(RoutingRoute, pk=route_id, plan_id=plan_id)
    response = HttpResponse(single_route_csv(route), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="route-plan-{plan_id}-route-{route.route_number}.csv"'
    return response
