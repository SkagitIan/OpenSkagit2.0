from django.urls import path

from . import views

app_name = "routing"

urlpatterns = [
    path("routes/", views.routes_page, name="routes"),
    path("routes/import/", views.import_file, name="import"),
    path("routes/plan/", views.create_plan, name="create_plan"),
    path("routes/plans/", views.plans_list, name="plans"),
    path("routes/plan/<int:plan_id>/optimize/", views.optimize_plan, name="optimize_plan"),
    path("routes/plan/<int:plan_id>/route/<int:route_id>/optimize/", views.optimize_route, name="optimize_route"),
    path("routes/plan/<int:plan_id>/move-stop/", views.move_stop, name="move_stop"),
    path("routes/plan/<int:plan_id>/stop/<int:stop_id>/lock/", views.lock_stop, name="lock_stop"),
    path("routes/plan/<int:plan_id>/stop/<int:stop_id>/remove/", views.remove_stop, name="remove_stop"),
    path("routes/plan/<int:plan_id>/add-stop/", views.add_stop, name="add_stop"),
    path("routes/plan/<int:plan_id>/available-stops/", views.available_stops, name="available_stops"),
    path("routes/plan/<int:plan_id>/", views.plan_detail, name="plan_detail"),
    path("routes/plan/<int:plan_id>/export/", views.export_plan, name="export_plan"),
]
