from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse

from apps.composer.metrics import METRICS_PLATFORMS
from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import PublishError
from providers.threads import ThreadsProvider
from providers.types import PostType, PublishContent


@pytest.fixture(autouse=True)
def forbid_external_api(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not call external provider APIs")

    monkeypatch.setattr(SocialProvider, "_request", fail)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


@pytest.mark.django_db
def test_threads_connect_uses_own_app_and_is_allowed_by_csp(client, settings, org_owner, organization):
    settings.CSP_REPORT_ONLY = False
    settings.PLATFORM_CREDENTIALS_FROM_ENV = {"threads": {"app_id": "threads-app", "app_secret": "s"}}
    workspace = Workspace.objects.create(organization=organization, name="Threads workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client.force_login(org_owner)
    response = client.post(
        reverse("social_accounts:connect", kwargs={"workspace_id": workspace.id}), {"platform": "threads"}
    )
    target = urlsplit(response["Location"])
    assert target.netloc == "threads.net"
    assert parse_qs(target.query)["client_id"] == ["threads-app"]
    assert parse_qs(target.query)["redirect_uri"][0].endswith("/social-accounts/callback/threads/")
    form_action = next(
        part.strip() for part in response["Content-Security-Policy"].split(";") if part.strip().startswith("form-action ")
    )
    assert {"https://threads.net", "https://www.threads.net"} <= set(form_action.split())


def test_threads_settings_use_dedicated_env_vars():
    from django.conf import settings

    from config.settings import base

    assert base._THREADS_CREDENTIALS is not base._META_CREDENTIALS
    assert set(settings.PLATFORM_CREDENTIALS_FROM_ENV["threads"]) == {"app_id", "app_secret"}


def test_video_waits_for_container_before_publishing():
    calls = []
    statuses = iter(["IN_PROGRESS", "FINISHED"])

    def fake_request(self, method, url, **kwargs):
        calls.append((method, url.rsplit("/", 1)[-1]))
        if method == "GET":
            return _response({"status": next(statuses)})
        if url.endswith("/threads"):
            return _response({"id": "container-1"})
        return _response({"id": "thread-1"})

    provider = ThreadsProvider({"app_id": "a", "app_secret": "b"})
    with patch.object(SocialProvider, "_request", fake_request), patch("providers.threads.time.sleep"):
        result = provider.publish_post(
            "t",
            PublishContent(
                text="Vídeo",
                post_type=PostType.VIDEO,
                media_urls=["https://x/v.mp4"],
                extra={"user_id": "u1"},
            ),
        )
    assert result.platform_post_id == "thread-1"
    assert calls == [("POST", "threads"), ("GET", "container-1"), ("GET", "container-1"), ("POST", "threads_publish")]


def test_container_error_stops_before_publishing():
    def fake_request(self, method, url, **kwargs):
        if method == "GET":
            return _response({"status": "ERROR", "error_message": "formato inválido"})
        if url.endswith("/threads"):
            return _response({"id": "c1"})
        raise AssertionError("must not publish")

    provider = ThreadsProvider({"app_id": "a", "app_secret": "b"})
    with patch.object(SocialProvider, "_request", fake_request), pytest.raises(PublishError, match="formato"):
        provider.publish_post(
            "t",
            PublishContent(post_type=PostType.IMAGE, media_urls=["https://x/a.jpg"], extra={"user_id": "u1"}),
        )


def test_carousel_detects_signed_video_urls():
    created = []

    def fake_request(self, method, url, **kwargs):
        if method == "GET":
            return _response({"status": "FINISHED"})
        if url.endswith("/threads"):
            created.append(kwargs["data"])
            return _response({"id": f"c{len(created)}"})
        return _response({"id": "thread-1"})

    provider = ThreadsProvider({"app_id": "a", "app_secret": "b"})
    with patch.object(SocialProvider, "_request", fake_request):
        provider.publish_post(
            "t",
            PublishContent(
                post_type=PostType.CAROUSEL,
                media_urls=["https://x/a.jpg", "https://x/v.mp4?sig=1"],
                extra={"user_id": "u1"},
            ),
        )
    assert created[1]["media_type"] == "VIDEO" and created[1]["video_url"].endswith("?sig=1")


def test_threads_metrics_enabled():
    assert "threads" in METRICS_PLATFORMS


def _signed_request(payload, secret):
    import base64
    import hashlib
    import hmac
    import json

    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=") + "." + encoded


@pytest.fixture
def threads_account(organization):
    from apps.social_accounts.models import SocialAccount

    workspace = Workspace.objects.create(organization=organization, name="Threads callbacks")
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="threads",
        account_platform_id="777",
        account_name="Jobz Threads",
        connection_status="connected",
        oauth_access_token="secret-token",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["social_accounts:threads_uninstall", "social_accounts:threads_delete"])
def test_threads_callbacks_disconnect_account(client, settings, threads_account, route):
    settings.PLATFORM_CREDENTIALS_FROM_ENV = {"threads": {"app_id": "a", "app_secret": "threads-secret"}}
    signed = _signed_request({"user_id": "777", "algorithm": "HMAC-SHA256"}, "threads-secret")

    response = client.post(reverse(route), {"signed_request": signed})

    assert response.status_code == 200
    threads_account.refresh_from_db()
    assert threads_account.connection_status == "disconnected"
    assert threads_account.oauth_access_token == ""
    if route.endswith("delete"):
        body = response.json()
        assert body["confirmation_code"] and "/threads/delete/status/" in body["url"]


@pytest.mark.django_db
def test_threads_callback_rejects_bad_signature(client, settings, threads_account):
    settings.PLATFORM_CREDENTIALS_FROM_ENV = {"threads": {"app_id": "a", "app_secret": "threads-secret"}}
    forged = _signed_request({"user_id": "777"}, "wrong-secret")
    response = client.post(reverse("social_accounts:threads_uninstall"), {"signed_request": forged})
    assert response.status_code == 400
    threads_account.refresh_from_db()
    assert threads_account.connection_status == "connected"
