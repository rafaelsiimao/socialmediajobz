"""URL patterns for the Insights page."""

from django.urls import path

from . import views

app_name = "insights"

urlpatterns = [
    path("refresh-followers/", views.refresh_followers, name="refresh_followers"),
    path("", views.insights_page, name="page"),
    path("export.csv", views.export_csv, name="export_csv"),
    path("import-history/", views.import_history, name="import_history"),
]
