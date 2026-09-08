from django.urls import path

from . import views

app_name = "routing"

urlpatterns = [
    path("routes/", views.routes_page, name="routes"),
    path("routes/import/", views.import_file, name="import"),
    path("routes/plan/", views.create_plan, name="create_plan"),
    path("routes/plan/<int:plan_id>/", views.plan_detail, name="plan_detail"),
    path("routes/plan/<int:plan_id>/export/", views.export_plan, name="export_plan"),
]
