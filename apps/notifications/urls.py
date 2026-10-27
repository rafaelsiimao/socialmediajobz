from django.urls import path

from . import email_preview, views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("drawer/", views.notification_drawer, name="drawer"),
    path("unread-count/", views.unread_count, name="unread_count"),
    path("mark-all-read/", views.mark_all_read, name="mark_all_read"),
    path("<uuid:notification_id>/read/", views.mark_as_read, name="mark_as_read"),
    path("preferences/", views.preferences, name="preferences"),
    path("email-preview/", email_preview.email_preview_index, name="email_preview_index"),
    path("email-preview/<slug:name>/", email_preview.email_preview, name="email_preview"),
]
