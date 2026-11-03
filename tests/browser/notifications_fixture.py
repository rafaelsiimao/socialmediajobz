"""Render real notification templates with synthetic, unsaved data; no database writes."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from django.template.loader import render_to_string  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.notifications.models import Notification  # noqa: E402

notification = Notification(
    event_type="post_failed",
    title="Falha sintética",
    body="Token expirado",
    created_at=timezone.now(),
    data={"action_url": "https://notifications.local/details/"},
)
context = {
    "notifications": [notification],
    "total": 1,
    "page": 1,
    "csrf_token": "a" * 64,
    "unread_notification_count": 1,
    "user": SimpleNamespace(is_authenticated=True, name="Teste", email="test@example.com"),
    "request": SimpleNamespace(
        workspace=None, resolver_match=SimpleNamespace(url_name="list", app_name="notifications")
    ),
}
history = render_to_string("notifications/history.html", context)
drawer = render_to_string("notifications/partials/drawer.html", context)
notification.is_read = True
print(
    json.dumps(
        {
            "history": history,
            "drawer": drawer,
            "read_history": render_to_string("notifications/partials/history_list.html", context),
            "read_drawer": render_to_string("notifications/partials/drawer.html", context),
        }
    )
)
