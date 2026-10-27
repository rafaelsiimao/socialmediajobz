from django.urls import path

from . import threads_callbacks, views

app_name = "social_accounts"

urlpatterns = [
    # Workspace-scoped views
    path(
        "<uuid:workspace_id>/",
        views.account_list,
        name="list",
    ),
    path(
        "<uuid:workspace_id>/connect/",
        views.connect_platform,
        name="connect",
    ),
    path(
        "<uuid:workspace_id>/connect/bluesky/",
        views.connect_bluesky,
        name="connect_bluesky",
    ),
    path(
        "<uuid:workspace_id>/connect/mastodon/",
        views.connect_mastodon,
        name="connect_mastodon",
    ),
    # Threads app settings: uninstall / delete-data callbacks (signed by Meta)
    path("threads/uninstall/", threads_callbacks.threads_uninstall, name="threads_uninstall"),
    path("threads/delete/", threads_callbacks.threads_delete, name="threads_delete"),
    path("threads/delete/status/", threads_callbacks.threads_delete_status, name="threads_delete_status"),
    # OAuth callback (not workspace-scoped - platform redirects here)
    path(
        "callback/<str:platform>/",
        views.oauth_callback,
        name="oauth_callback",
    ),
    # Account selection (Facebook multi-page)
    path(
        "select-account/",
        views.select_account,
        name="select_account",
    ),
    # Per-account actions
    path(
        "<uuid:workspace_id>/<uuid:account_id>/reconnect/",
        views.reconnect,
        name="reconnect",
    ),
    path(
        "<uuid:workspace_id>/<uuid:account_id>/disconnect/",
        views.disconnect,
        name="disconnect",
    ),
]
