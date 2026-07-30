from django.urls import path
from . import views
app_name = "livefire"
urlpatterns = [
 path("", views.dashboard, name="dashboard"), path("scenarios/new/", views.scenario_create, name="scenario_create"),
 path("scenarios/<int:pk>/clone/", views.scenario_clone, name="scenario_clone"), path("scenarios/<int:pk>/archive/", views.scenario_archive, name="scenario_archive"), path("compare/", views.compare, name="compare"),
 path("scenarios/<int:scenario_pk>/<str:kind>/new/", views.related_edit, name="related_new"), path("scenarios/<int:scenario_pk>/<str:kind>/<int:pk>/", views.related_edit, name="related_edit"),
 path("quotes/", views.quotes, name="quotes"), path("vendor/<str:token>/", views.vendor_quote, name="vendor_quote"), path("quotes/<int:pk>/prefer/", views.prefer_quote, name="prefer_quote"),
 path("scenarios/<int:pk>/publish/", views.publish, name="publish"), path("shared/<str:token>/", views.shared, name="shared"),
]
