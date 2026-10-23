from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.composer.importer import import_instagram_history
from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.instagram import InstagramProvider


@pytest.fixture(autouse=True)
def forbid_external_api(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not call external provider APIs")

    monkeypatch.setattr(SocialProvider, "_request", fail)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _ts(days_ago):
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


def test_list_media_follows_paging_and_stops_at_since():
    pages = {
        "first": {
            "data": [{"id": "m1", "timestamp": _ts(1)}, {"id": "m2", "timestamp": _ts(5)}],
            "paging": {"next": "https://graph.facebook.com/v21.0/ig/media?after=abc"},
        },
        "second": {
            "data": [{"id": "m3", "timestamp": _ts(10)}, {"id": "m4", "timestamp": _ts(400)}],
            "paging": {"next": "https://graph.facebook.com/v21.0/ig/media?after=def"},
        },
    }
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append((url, kwargs.get("params")))
        return _response(pages["second"] if "after=abc" in url else pages["first"])

    with patch.object(SocialProvider, "_request", fake_request):
        items = InstagramProvider({"ig_user_id": "ig"}).list_media("token", since=datetime.now(UTC) - timedelta(days=365))

    assert [m["id"] for m in items] == ["m1", "m2", "m3"]
    assert calls[0][1]["fields"].startswith("id,caption")
    assert calls[1][1] is None  # next URL already carries the query
    assert len(calls) == 2  # stopped at the old post, did not follow the second "next"


@pytest.fixture
def ig_account(organization, org_owner):
    workspace = Workspace.objects.create(organization=organization, name="Import workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-1",
        account_name="Jobz",
        connection_status="connected",
    )


def _media(media_id, days_ago, **extra):
    return {
        "id": media_id,
        "caption": f"Legenda {media_id}",
        "media_type": "IMAGE",
        "media_product_type": "FEED",
        "media_url": f"https://cdn.example.com/{media_id}.jpg",
        "permalink": f"https://www.instagram.com/p/{media_id}/",
        "timestamp": timezone.now() - timedelta(days=days_ago),
        **extra,
    }


@pytest.mark.django_db
def test_import_creates_published_posts_without_duplicates(ig_account, org_owner):
    system_post = Post.objects.create(workspace=ig_account.workspace, author=org_owner, caption="Pelo sistema")
    system_post.platform_posts.create(
        social_account=ig_account, status="published", platform_post_id="m-system", published_at=timezone.now()
    )
    provider = MagicMock()
    provider.credentials = {}
    provider.list_media.return_value = [
        _media("m-new", 2),
        _media("m-reel", 3, media_type="VIDEO", media_product_type="REELS", thumbnail_url="https://cdn.example.com/c.jpg"),
        _media("m-system", 4),
    ]

    with (
        patch("apps.composer.importer._provider_for_account", return_value=provider),
        patch("apps.composer.importer.refresh_platform_post_metrics") as refresh,
    ):
        first = import_instagram_history(ig_account)
        second = import_instagram_history(ig_account)

    assert first == {"created": 2, "updated": 0}
    assert second == {"created": 0, "updated": 2}
    assert refresh.call_count == 2
    assert provider.credentials["ig_user_id"] == "ig-1"

    new = PlatformPost.objects.get(platform_post_id="m-new")
    assert new.status == "published" and new.post.author is None
    assert new.post.caption == "Legenda m-new"
    assert new.platform_extra["imported"] is True
    assert new.platform_extra["thumbnail_url"] == "https://cdn.example.com/m-new.jpg"
    reel = PlatformPost.objects.get(platform_post_id="m-reel")
    assert reel.platform_extra["post_type"] == "reel"
    assert reel.platform_extra["thumbnail_url"] == "https://cdn.example.com/c.jpg"
    assert PlatformPost.objects.filter(platform_post_id="m-system").count() == 1


@pytest.mark.django_db
def test_import_button_queues_instagram_accounts(client, ig_account, org_owner):
    client.force_login(org_owner)
    with patch("apps.composer.tasks.import_instagram_history_task") as task:
        response = client.post(
            reverse("insights:import_history", kwargs={"workspace_id": ig_account.workspace.id}), {"query": "period=7d"}
        )
    assert response.status_code == 302
    assert response.url.endswith("?period=7d")
    task.assert_called_once_with(str(ig_account.id))


@pytest.mark.django_db
def test_imported_post_shows_instagram_thumbnail_in_modal(client, ig_account, org_owner):
    post = Post.objects.create(workspace=ig_account.workspace, caption="Importado")
    pp = post.platform_posts.create(
        social_account=ig_account,
        status="published",
        platform_post_id="m-x",
        published_at=timezone.now(),
        platform_extra={"imported": True, "thumbnail_url": "https://cdn.example.com/x.jpg"},
    )
    client.force_login(org_owner)
    body = client.get(
        reverse(
            "calendar:published_post_detail",
            kwargs={"workspace_id": ig_account.workspace.id, "platform_post_id": pp.id},
        )
    ).content.decode()
    assert "https://cdn.example.com/x.jpg" in body
