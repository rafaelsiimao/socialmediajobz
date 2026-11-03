from datetime import timedelta
from unittest.mock import patch

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.notifications.models import EventType, Notification
from apps.publisher.engine import MAX_RETRIES, PublishEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def platform_post(organization, org_owner):
    workspace = Workspace.objects.create(organization=organization, name="Publicações")
    WorkspaceMembership.objects.create(workspace=workspace, user=org_owner, workspace_role="owner")
    account = SocialAccount.objects.create(
        workspace=workspace, platform="facebook", account_name="Página de teste", account_platform_id="123"
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, title="Campanha")
    return PlatformPost.objects.create(
        post=post, social_account=account, status="scheduled", scheduled_at=timezone.now() - timedelta(minutes=1)
    )


def test_exhausted_failure_notifies_author_with_error_and_post_link(platform_post, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    platform_post.retry_count = MAX_RETRIES
    platform_post.save()
    with patch.object(
        PublishEngine, "_dispatch_to_provider", return_value={"success": False, "error": "Token expirado"}
    ):
        PublishEngine()._publish_platform_post(platform_post)
    platform_post.refresh_from_db()
    assert platform_post.status == "failed"
    notification = Notification.objects.get(user=platform_post.post.author, event_type=EventType.POST_FAILED)
    assert "Token expirado" in notification.body
    assert "Página de teste" in notification.body
    assert notification.data["action_url"].endswith(
        reverse(
            "composer:compose_edit",
            kwargs={"workspace_id": platform_post.post.workspace_id, "post_id": platform_post.post_id},
        )
    )


def test_temporary_failure_does_not_send_terminal_alert(platform_post):
    PublishEngine()._schedule_retry(platform_post, "Falha temporária")
    assert not Notification.objects.filter(event_type=EventType.POST_FAILED).exists()


def test_success_clears_old_error_and_notifies(platform_post):
    platform_post.publish_error = "Falha antiga"
    platform_post.next_retry_at = timezone.now()
    platform_post.retry_count = 1
    platform_post.save()
    with patch.object(
        PublishEngine, "_dispatch_to_provider", return_value={"success": True, "platform_post_id": "remote-123"}
    ):
        result = PublishEngine()._publish_platform_post(platform_post)
    platform_post.refresh_from_db()
    assert result["success"]
    assert platform_post.publish_error == ""
    assert platform_post.next_retry_at is None
    assert Notification.objects.filter(user=platform_post.post.author, event_type=EventType.POST_PUBLISHED).count() == 1


def test_notification_failure_cannot_turn_success_into_retry(platform_post):
    with (
        patch.object(
            PublishEngine, "_dispatch_to_provider", return_value={"success": True, "platform_post_id": "remote-123"}
        ),
        patch("apps.notifications.engine.notify", side_effect=RuntimeError("notification unavailable")),
    ):
        result = PublishEngine()._publish_platform_post(platform_post)
    platform_post.refresh_from_db()
    assert result["success"]
    assert platform_post.status == "published"
    assert platform_post.retry_count == 0


def test_poll_does_not_bypass_retry_backoff(platform_post):
    PublishEngine()._schedule_retry(platform_post, "Aguarde")
    assert platform_post not in PublishEngine()._get_due_platform_posts()


def test_initial_posts_still_appear_in_poll(platform_post):
    assert platform_post in PublishEngine()._get_due_platform_posts()


def test_editor_shows_failure_reason(platform_post, client, org_owner):
    platform_post.status = "failed"
    platform_post.publish_error = "Falha de publicação sintética"
    platform_post.save()
    client.force_login(org_owner)
    response = client.get(
        reverse(
            "composer:compose_edit",
            kwargs={"workspace_id": platform_post.post.workspace_id, "post_id": platform_post.post_id},
        )
    )
    assert response.status_code == 200
    assert "Falha de publicação sintética" in response.content.decode()


def test_drawer_marks_read_without_intercepting_navigation(user):
    notification = Notification.objects.create(
        user=user, event_type="post_failed", title="Falhou", data={"action_url": "/workspace/example/compose/example/"}
    )
    html = render_to_string("notifications/partials/drawer.html", {"notifications": [notification]})
    assert "hx-post=" not in html.split('href="/workspace/example/compose/example/"', 1)[1].split("</a>", 1)[0]


def test_mark_all_from_history_returns_history(client, user):
    client.force_login(user)
    Notification.objects.create(user=user, event_type="post_failed", title="Falha de teste")
    response = client.post(
        "/notifications/mark-all-read/", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="notification-history-list"
    )
    assert b"notification-drawer-content" not in response.content
    assert b"Falha de teste" in response.content


@pytest.mark.parametrize("page", ["abc", "0", "-1"])
def test_history_handles_invalid_page(client, user, page):
    client.force_login(user)
    response = client.get("/notifications/", {"page": page})
    assert response.status_code == 200


def test_retry_task_is_registered_once():
    from background_task.models import Task
    from django.apps import apps

    config = apps.get_app_config("notifications")
    config._register_notification_tasks(sender=config)
    config._register_notification_tasks(sender=config)
    task = Task.objects.get(verbose_name="retry_notification_deliveries")
    assert task.repeat == 60


def test_mark_all_drawer_is_not_rejected_as_post(client, user):
    client.force_login(user)
    Notification.objects.create(user=user, event_type="post_failed", title="Falha de teste")
    response = client.post(
        "/notifications/mark-all-read/", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="notification-drawer-content"
    )
    assert response.status_code == 200
    assert b"Falha de teste" in response.content
    assert not Notification.objects.filter(user=user, is_read=False).exists()


def test_history_read_action_keeps_item_and_refreshes_state(client, user):
    client.force_login(user)
    notification = Notification.objects.create(user=user, event_type="post_failed", title="Registro preservado")
    response = client.post(
        f"/notifications/{notification.id}/read/", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="notification-history-list"
    )
    assert response.status_code == 200
    assert b"Registro preservado" in response.content
    notification.refresh_from_db()
    assert notification.is_read


def test_mark_all_preserves_unread_filter(client, user):
    client.force_login(user)
    Notification.objects.create(user=user, event_type="post_failed", title="Antes não lida")
    response = client.post(
        "/notifications/mark-all-read/",
        {"read_status": "unread"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="notification-history-list",
    )
    assert response.status_code == 200
    assert "Antes não lida" not in response.content.decode()


def test_read_action_cannot_change_other_users_notification(client, user, django_user_model):
    client.force_login(user)
    other = django_user_model.objects.create_user(email="other@example.com", password="testpass123")
    notification = Notification.objects.create(user=other, event_type="post_failed", title="Privada")
    client.post(f"/notifications/{notification.id}/read/")
    notification.refresh_from_db()
    assert not notification.is_read


def test_rate_limit_is_recorded_in_publish_log(platform_post):
    from apps.publisher.models import PublishLog, RateLimitState

    RateLimitState.objects.create(
        social_account=platform_post.social_account,
        platform="facebook",
        requests_remaining=0,
        window_resets_at=timezone.now() + timedelta(minutes=10),
    )
    with patch.object(PublishEngine, "_dispatch_to_provider") as dispatch:
        result = PublishEngine()._publish_platform_post(platform_post)
    dispatch.assert_not_called()
    assert not result["success"]
    assert "Rate limited" in PublishLog.objects.get(platform_post=platform_post).error_message


def test_due_retry_is_processed_once_and_notifies_success(platform_post):
    platform_post.retry_count = 1
    platform_post.next_retry_at = timezone.now() - timedelta(seconds=1)
    platform_post.publish_error = "Falha temporária"
    platform_post.save()
    engine = PublishEngine()
    assert platform_post not in engine._get_due_platform_posts()
    with patch.object(
        engine, "_dispatch_to_provider", return_value={"success": True, "platform_post_id": "recovered"}
    ) as dispatch:
        engine._process_retries()
        engine._process_retries()
    dispatch.assert_called_once()
    platform_post.refresh_from_db()
    assert platform_post.status == "published"
    assert platform_post.publish_error == ""
    assert Notification.objects.filter(event_type="post_published").count() == 1


def test_email_delivery_retries_with_worker_entry_point(user, settings):
    from apps.notifications.engine import notify
    from apps.notifications.models import NotificationDelivery
    from apps.notifications.tasks import retry_notification_deliveries

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    with patch("apps.notifications.engine.EmailMultiAlternatives.send", side_effect=OSError("SMTP indisponível")):
        notification = notify(user, "post_failed", "Falhou")
    delivery = NotificationDelivery.objects.get(notification=notification, channel="email")
    assert delivery.status == "pending"
    delivery.next_retry_at = timezone.now() - timedelta(seconds=1)
    delivery.save()
    retry_notification_deliveries.now()
    delivery.refresh_from_db()
    assert delivery.status == "delivered"
    assert delivery.attempts == 2


def test_sidebar_has_live_unread_badge(client, user):
    client.force_login(user)
    response = client.get("/notifications/")
    assert b'x-data="notificationBell()"' in response.content
    assert b'x-init="startPolling()"' in response.content
