from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from apps.composer.metrics import METRICS_PLATFORMS
from apps.composer.models import Post
from apps.inbox.tasks import _account_credentials
from apps.members.models import WorkspaceMembership
from apps.publisher.engine import PublishEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import PublishError
from providers.instagram_personal import API_BASE, InstagramPersonalProvider
from providers.types import PostType, PublishContent, PublishResult


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


def _provider():
    return InstagramPersonalProvider({"app_id": "ig-app", "app_secret": "s", "ig_user_id": "me-1"})


def test_requests_insights_scope():
    assert "instagram_business_manage_insights" in _provider().required_scopes


def test_story_sequence_and_reel_rules():
    provider = _provider()
    calls = []

    def create(token, payload):
        calls.append(payload)
        return f"c{len(calls)}"

    with (
        patch.object(provider, "_create_container", side_effect=create),
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", side_effect=lambda t, c: PublishResult(f"m-{c}")),
    ):
        result = provider.publish_post(
            "t",
            PublishContent(
                text="ignorada",
                post_type=PostType.STORY,
                media_urls=["https://x/1.jpg", "https://x/2.mp4?sig=1"],
            ),
        )
    assert result.extra["story_ids"] == ["m-c1", "m-c2"]
    assert calls[1] == {"media_type": "STORIES", "video_url": "https://x/2.mp4?sig=1"}
    assert all("caption" not in payload for payload in calls)

    with patch.object(provider, "_create_container") as create_mock, pytest.raises(PublishError):
        provider.publish_post("t", PublishContent(post_type=PostType.REEL, media_urls=["https://x/a.jpg"]))
    create_mock.assert_not_called()


def test_reel_sends_collaborators():
    provider = _provider()
    with (
        patch.object(provider, "_create_container", return_value="c1") as create,
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", return_value=PublishResult("m1")),
    ):
        provider.publish_post(
            "t",
            PublishContent(
                text="Reel",
                post_type=PostType.REEL,
                media_urls=["https://x/v.mp4"],
                extra={"collaborators": ["@Parceiro"]},
            ),
        )
    payload = create.call_args.args[1]
    assert payload["media_type"] == "REELS" and payload["collaborators"] == ["parceiro"]


def test_metrics_use_current_insight_names():
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append(url)
        if url.endswith("/insights"):
            metric_names = kwargs["params"]["metric"].split(",")
            assert "impressions" not in metric_names and "engagement" not in metric_names
            return _response({"data": [{"name": "views", "values": [{"value": 90}]}]})
        return _response({"like_count": 4, "comments_count": 1, "media_product_type": "FEED", "permalink": "p"})

    with patch.object(SocialProvider, "_request", fake_request):
        metrics = _provider().get_post_metrics("t", "m1")
    assert calls[0].startswith(API_BASE)
    assert (metrics.impressions, metrics.likes, metrics.comments) == (90, 4, 1)


def test_list_media_and_inbox():
    media_page = {
        "data": [
            {
                "id": "m1",
                "timestamp": _ts(1),
                "comments": {
                    "data": [
                        {"id": "c1", "text": "Top!", "timestamp": _ts(1), "from": {"id": "fan", "username": "fan"}},
                        {"id": "c2", "text": "Valeu", "timestamp": _ts(1), "from": {"id": "me-1", "username": "eu"}},
                    ]
                },
            },
            {"id": "m-old", "timestamp": _ts(400)},
        ]
    }
    conversations = {
        "data": [
            {
                "id": "conv",
                "messages": {
                    "data": [
                        {"id": "d1", "message": "Oi", "created_time": _ts(1), "from": {"id": "igsid", "username": "cli"}}
                    ]
                },
            }
        ]
    }

    def fake_request(self, method, url, **kwargs):
        if url.endswith("/me/conversations"):
            assert kwargs["params"]["platform"] == "instagram"
            return _response(conversations)
        return _response(media_page)

    with patch.object(SocialProvider, "_request", fake_request):
        provider = _provider()
        media = provider.list_media("t", since=datetime.now(UTC) - timedelta(days=365))
        messages = provider.get_messages("t", since=datetime.now(UTC) - timedelta(days=30))

    assert [m["id"] for m in media] == ["m1"]
    assert {m.platform_message_id for m in messages} == {"c1", "d1"}
    dm = next(m for m in messages if m.message_type == "dm")
    assert dm.extra["sender_id"] == "igsid"


def test_replies_to_comment_and_dm():
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append((url, kwargs.get("json")))
        return _response({"id": "r1", "message_id": "mid"})

    with patch.object(SocialProvider, "_request", fake_request):
        provider = _provider()
        provider.reply_to_message("t", "c1", "Obrigado!", extra={"kind": "comment"})
        provider.reply_to_message("t", "d1", "Oi!", extra={"kind": "dm", "sender_id": "igsid"})
    assert calls[0][0].endswith("/c1/replies")
    assert calls[1][0].endswith("/me/messages")
    assert calls[1][1]["recipient"] == {"id": "igsid"}


def test_app_treats_instagram_login_like_instagram():
    assert "instagram_personal" in METRICS_PLATFORMS
    assert PublishEngine._resolve_post_type("instagram_personal", {}, 1, "video") == PostType.REEL
    account = SocialAccount(platform="instagram_personal", account_platform_id="17841")
    assert account.is_instagram
    assert _account_credentials(account) == {"ig_user_id": "17841"}


@pytest.mark.django_db
def test_composer_format_and_import_button_work_for_instagram_login(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="IG Login")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram_personal",
        account_platform_id="17841",
        account_name="Cliente",
        connection_status="connected",
    )
    client.force_login(org_owner)

    client.post(
        reverse("composer:save_post", kwargs={"workspace_id": workspace.id}),
        {"caption": "Story", "action": "save_draft", "selected_accounts": str(account.id), f"ig_format_{account.id}": "story"},
    )
    post = Post.objects.get(workspace=workspace)
    assert post.platform_posts.get().platform_extra["post_type"] == "story"
    editor = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id}))
    assert f'name="ig_format_{account.id}"'.encode() in editor.content

    with patch("apps.composer.tasks.import_instagram_history_task") as task:
        client.post(reverse("insights:import_history", kwargs={"workspace_id": workspace.id}))
    task.assert_called_once_with(str(account.id))
