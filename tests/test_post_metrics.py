from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.composer.metrics import platform_posts_needing_metrics, refresh_platform_post_metrics
from apps.composer.models import PlatformPostMetrics, Post
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import APIError
from providers.facebook import FacebookProvider
from providers.instagram import InstagramProvider
from providers.types import PostMetrics


@pytest.fixture(autouse=True)
def forbid_external_api(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not call external provider APIs")

    monkeypatch.setattr(SocialProvider, "_request", fail)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_instagram_metrics_use_current_insight_names():
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append((url, kwargs["params"]))
        if url.endswith("/insights"):
            return _response(
                {
                    "data": [
                        {"name": "reach", "values": [{"value": 120}]},
                        {"name": "views", "values": [{"value": 300}]},
                        {"name": "likes", "values": [{"value": 15}]},
                        {"name": "comments", "values": [{"value": 4}]},
                        {"name": "shares", "values": [{"value": 2}]},
                        {"name": "saved", "values": [{"value": 7}]},
                        {"name": "total_interactions", "values": [{"value": 28}]},
                    ]
                }
            )
        return _response({"like_count": 15, "comments_count": 4, "media_product_type": "FEED"})

    with patch.object(SocialProvider, "_request", fake_request):
        metrics = InstagramProvider({}).get_post_metrics("token", "media-1")

    insight_params = calls[1][1]["metric"].split(",")
    assert "impressions" not in insight_params and "engagement" not in insight_params
    assert (metrics.impressions, metrics.reach, metrics.likes, metrics.saves) == (300, 120, 15, 7)
    assert metrics.engagements == 28


def test_instagram_metrics_fall_back_to_counters_when_insights_fail():
    def fake_request(self, method, url, **kwargs):
        if url.endswith("/insights"):
            raise APIError("(#10) Not enough viewers", status_code=400)
        return _response({"like_count": 9, "comments_count": 2, "media_product_type": "STORY"})

    with patch.object(SocialProvider, "_request", fake_request):
        metrics = InstagramProvider({}).get_post_metrics("token", "media-1")

    assert (metrics.likes, metrics.comments, metrics.reach) == (9, 2, 0)
    assert "Not enough viewers" in metrics.extra["insights_error"]


def test_facebook_metrics_read_post_counters():
    def fake_request(self, method, url, **kwargs):
        assert not url.endswith("/insights")
        return _response(
            {
                "shares": {"count": 3},
                "comments": {"summary": {"total_count": 5}},
                "reactions": {"summary": {"total_count": 20}},
            }
        )

    with patch.object(SocialProvider, "_request", fake_request):
        metrics = FacebookProvider({}).get_post_metrics("token", "page_post")

    assert (metrics.likes, metrics.comments, metrics.shares, metrics.engagements) == (20, 5, 3, 28)


@pytest.fixture
def published_post(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Metrics workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    account = SocialAccount.objects.create(
        workspace=workspace, platform="instagram", account_platform_id="ig-test", account_name="Jobz"
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Publicado", scheduled_at=timezone.now())
    platform_post = post.platform_posts.create(
        social_account=account,
        status="published",
        platform_post_id="media-1",
        published_at=timezone.now(),
    )
    client.force_login(org_owner)
    return workspace, platform_post


@pytest.mark.django_db
def test_refresh_stores_snapshot_and_sent_tab_shows_it(client, published_post):
    workspace, platform_post = published_post
    assert list(platform_posts_needing_metrics()) == [platform_post]

    fake_provider = MagicMock()
    fake_provider.get_post_metrics.return_value = PostMetrics(
        impressions=300, reach=120, likes=15, comments=4, saves=7, extra={"insights_error": ""}
    )
    with patch("apps.composer.metrics.get_provider", return_value=fake_provider):
        refresh_platform_post_metrics(platform_post)

    snapshot = PlatformPostMetrics.objects.get(platform_post=platform_post)
    assert (snapshot.views, snapshot.reach, snapshot.likes, snapshot.saves) == (300, 120, 15, 7)
    assert snapshot.fetched_at is not None

    response = client.get(reverse("calendar:publish_tab_sent", kwargs={"workspace_id": workspace.id}))
    assert response.status_code == 200
    assert "Desempenho" in response.content.decode()
    assert "300" in response.content.decode()


@pytest.mark.django_db
def test_refresh_records_error_without_raising(published_post):
    _, platform_post = published_post
    fake_provider = MagicMock()
    fake_provider.get_post_metrics.side_effect = APIError("token expired", status_code=401)
    with patch("apps.composer.metrics.get_provider", return_value=fake_provider):
        snapshot = refresh_platform_post_metrics(platform_post)

    assert snapshot.fetched_at is None
    assert "token expired" in snapshot.last_error


@pytest.mark.django_db
def test_published_post_opens_detail_modal_with_metrics(client, published_post):
    workspace, platform_post = published_post
    PlatformPostMetrics.objects.create(
        platform_post=platform_post,
        likes=42,
        reach=99,
        fetched_at=timezone.now(),
        raw={"permalink": "https://www.instagram.com/p/abc/"},
    )
    detail_url = reverse(
        "calendar:published_post_detail",
        kwargs={"workspace_id": workspace.id, "platform_post_id": platform_post.id},
    )

    calendar_page = client.get(reverse("calendar:calendar", kwargs={"workspace_id": workspace.id}), {"view": "month"})
    assert detail_url in calendar_page.content.decode()

    body = client.get(detail_url).content.decode()
    assert "Publicado" in body and "Desempenho" in body
    assert "42" in body and "99" in body
    assert "https://www.instagram.com/p/abc/" in body


@pytest.mark.django_db
def test_detail_modal_rejects_unpublished_and_other_workspaces(client, published_post, organization):
    workspace, platform_post = published_post
    url = reverse(
        "calendar:published_post_detail",
        kwargs={"workspace_id": workspace.id, "platform_post_id": platform_post.id},
    )
    platform_post.status = "scheduled"
    platform_post.save(update_fields=["status"])
    assert client.get(url).status_code == 404

    other = Workspace.objects.create(organization=organization, name="Other")
    other_url = reverse(
        "calendar:published_post_detail",
        kwargs={"workspace_id": other.id, "platform_post_id": platform_post.id},
    )
    assert client.get(other_url).status_code in (403, 404)


@pytest.mark.django_db
def test_refresh_button_fetches_metrics(client, published_post):
    workspace, platform_post = published_post
    fake_provider = MagicMock()
    fake_provider.get_post_metrics.return_value = PostMetrics(likes=7, comments=1, extra={})
    with patch("apps.composer.metrics.get_provider", return_value=fake_provider):
        response = client.post(
            reverse(
                "calendar:published_post_refresh_metrics",
                kwargs={"workspace_id": workspace.id, "platform_post_id": platform_post.id},
            )
        )
    assert response.status_code == 200
    assert PlatformPostMetrics.objects.get(platform_post=platform_post).likes == 7
