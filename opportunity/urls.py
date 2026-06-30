from django.urls import path

from . import views


urlpatterns = [
    path("login/", views.ParcelBookLoginView.as_view(), name="opportunity_login"),
    path("logout/", views.ParcelBookLogoutView.as_view(), name="opportunity_logout"),
    path("", views.home, name="opportunity_home"),
    path("explore/", views.explore, name="opportunity_explore"),
    path("ai-search/", views.ai_search, name="opportunity_ai_search"),
    path("ai-search/<int:search_id>/", views.ai_search_detail, name="opportunity_ai_search_detail"),
    path("ai-search/<int:search_id>/save/", views.save_ai_search, name="opportunity_ai_search_save"),
    path("ai-search/<int:search_id>/refresh/", views.refresh_ai_search, name="opportunity_ai_search_refresh"),
    path("ai-search/<int:search_id>/feedback/", views.ai_search_feedback, name="opportunity_ai_search_feedback"),
    path("newsletter-preview/", views.newsletter_preview, name="opportunity_newsletter_preview"),
    path("parcels/<str:parcel_number>/", views.parcel, name="opportunity_parcel_detail"),
    path("watchlist/", views.watchlist, name="opportunity_watchlist"),
    path("save/", views.save_parcel, name="opportunity_save"),
    path("settings/", views.notification_settings, name="opportunity_settings"),
]
