from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.composer.models import Post
from apps.members.models import WorkspaceMembership
from apps.publisher.engine import PublishEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import PublishError
from providers.instagram import InstagramProvider
from providers.types import PostType, PublishContent, PublishResult


@pytest.fixture(autouse=True)
def forbid_external_api(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not call external provider APIs")

    monkeypatch.setattr(SocialProvider, "_request", fail)


@pytest.fixture
def instagram_editor(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Story workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    account = SocialAccount.objects.create(
        workspace=workspace, platform="instagram", account_platform_id="ig-test", account_name="Jobz"
    )
    client.force_login(org_owner)
    return workspace, account


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
def test_story_format_is_saved_and_reloaded(client, instagram_editor, endpoint):
    workspace, account = instagram_editor
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.id}),
        {
            "caption": "Story draft",
            "action": "save_draft",
            "selected_accounts": str(account.id),
            f"ig_format_{account.id}": "story",
        },
    )
    assert response.status_code in (200, 204, 302)
    post = Post.objects.get(workspace=workspace)
    assert post.platform_posts.get().platform_extra["post_type"] == "story"

    editor = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id}))
    assert b"igFormat: 'story'" in editor.content


@pytest.mark.django_db
def test_switching_back_to_feed_clears_story_and_story_drops_collaborators(client, instagram_editor, org_owner):
    workspace, account = instagram_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Draft")
    platform_post = post.platform_posts.create(social_account=account, platform_extra={"collaborators": ["partner"]})
    url = reverse("composer:save_post_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id})

    client.post(
        url,
        {"caption": "Draft", "action": "save_draft", "selected_accounts": str(account.id), f"ig_format_{account.id}": "story"},
    )
    platform_post.refresh_from_db()
    assert platform_post.platform_extra == {"post_type": "story"}

    client.post(
        url,
        {"caption": "Draft", "action": "save_draft", "selected_accounts": str(account.id), f"ig_format_{account.id}": "feed"},
    )
    platform_post.refresh_from_db()
    assert "post_type" not in platform_post.platform_extra


@pytest.mark.django_db
def test_story_with_collaborators_is_rejected(client, instagram_editor):
    workspace, account = instagram_editor
    response = client.post(
        reverse("composer:save_post", kwargs={"workspace_id": workspace.id}),
        {
            "caption": "Story",
            "selected_accounts": str(account.id),
            f"ig_format_{account.id}": "story",
            f"ig_collaborators_{account.id}": "@partner",
        },
    )
    assert response.status_code == 400
    assert "ig_format" in response.json()["errors"]


def test_engine_resolves_story_hint():
    post_type = PublishEngine._resolve_post_type("instagram", {"post_type": "story"}, 1, "image")
    assert post_type == PostType.STORY


@pytest.mark.parametrize(
    ("url", "media_key"),
    [
        ("https://cdn.example.com/story.jpg?X-Amz-Signature=abc", "image_url"),
        ("https://cdn.example.com/story.MP4?X-Amz-Signature=abc", "video_url"),
    ],
)
def test_story_payload_has_no_caption_and_detects_signed_video(url, media_key):
    provider = InstagramProvider({"ig_user_id": "123"})
    content = PublishContent(text="Legenda ignorada", post_type=PostType.STORY, media_urls=[url])
    with (
        patch.object(provider, "_create_container", return_value="container") as create,
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", return_value=PublishResult("published")),
    ):
        provider.publish_post("token", content)
    payload = create.call_args.args[2]
    assert payload["media_type"] == "STORIES"
    assert payload[media_key] == url
    assert "caption" not in payload


def test_story_sequence_limits():
    provider = InstagramProvider({"ig_user_id": "123"})
    for urls in ([], [f"https://example.com/{i}.jpg" for i in range(11)]):
        content = PublishContent(post_type=PostType.STORY, media_urls=urls)
        with patch.object(provider, "_create_container") as create, pytest.raises(PublishError):
            provider.publish_post("token", content)
        create.assert_not_called()


def test_story_sequence_prepares_all_media_before_publishing_in_order():
    provider = InstagramProvider({"ig_user_id": "123"})
    urls = ["https://example.com/1.jpg", "https://example.com/2.mp4", "https://example.com/3.jpg"]
    events = []

    def create(token, ig_user_id, payload):
        events.append(("create", payload))
        return f"c{len(events)}"

    def publish(token, ig_user_id, container_id):
        events.append(("publish", container_id))
        return PublishResult(f"media-{container_id}", url=f"https://instagram.com/{container_id}")

    with (
        patch.object(provider, "_create_container", side_effect=create),
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", side_effect=publish),
    ):
        result = provider.publish_post("token", PublishContent(post_type=PostType.STORY, media_urls=urls))

    kinds = [kind for kind, _ in events]
    assert kinds == ["create", "create", "create", "publish", "publish", "publish"]
    assert "video_url" in events[1][1] and "image_url" in events[0][1]
    assert [arg for kind, arg in events if kind == "publish"] == ["c1", "c2", "c3"]
    assert result.platform_post_id == "media-c1"
    assert result.extra["story_ids"] == ["media-c1", "media-c2", "media-c3"]


def test_story_sequence_failure_before_publishing_raises_for_safe_retry():
    provider = InstagramProvider({"ig_user_id": "123"})
    urls = ["https://example.com/1.jpg", "https://example.com/2.jpg"]
    with (
        patch.object(provider, "_create_container", side_effect=["c1", PublishError("bad media")]),
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container") as publish,
        pytest.raises(PublishError),
    ):
        provider.publish_post("token", PublishContent(post_type=PostType.STORY, media_urls=urls))
    publish.assert_not_called()


def test_story_sequence_partial_publish_is_reported_without_retry():
    provider = InstagramProvider({"ig_user_id": "123"})
    urls = ["https://example.com/1.jpg", "https://example.com/2.jpg"]
    with (
        patch.object(provider, "_create_container", side_effect=["c1", "c2"]),
        patch.object(provider, "_wait_for_container"),
        patch.object(
            provider, "_publish_container", side_effect=[PublishResult("m1"), PublishError("limite atingido")]
        ),
    ):
        result = provider.publish_post("token", PublishContent(post_type=PostType.STORY, media_urls=urls))
    assert result.platform_post_id == "m1"
    assert result.extra["story_ids"] == ["m1"]
    assert "1 de 2 Stories" in result.extra["story_errors"]


@pytest.mark.django_db
def test_preview_renders_story_layout_when_selected(client, instagram_editor):
    workspace, account = instagram_editor
    url = reverse("composer:preview", kwargs={"workspace_id": workspace.id})
    story = client.get(url, {"selected_accounts": str(account.id), f"ig_format_{account.id}": "story"})
    feed = client.get(url, {"selected_accounts": str(account.id), f"ig_format_{account.id}": "feed"})
    assert "aspect-ratio: 9/16" in story.content.decode()
    assert "Enviar mensagem" in story.content.decode()
    assert "aspect-ratio: 9/16" not in feed.content.decode()


@pytest.mark.django_db
def test_reel_format_is_saved_reloaded_and_cleared(client, instagram_editor, org_owner):
    workspace, account = instagram_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Draft")
    platform_post = post.platform_posts.create(social_account=account)
    url = reverse("composer:save_post_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id})
    data = {"caption": "Draft", "action": "save_draft", "selected_accounts": str(account.id)}

    client.post(url, {**data, f"ig_format_{account.id}": "reel", f"ig_collaborators_{account.id}": "@partner"})
    platform_post.refresh_from_db()
    assert platform_post.platform_extra == {"post_type": "reel", "collaborators": ["partner"]}
    editor = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id}))
    assert b"igFormat: 'reel'" in editor.content

    client.post(url, {**data, f"ig_format_{account.id}": "feed", f"ig_collaborators_{account.id}": "@partner"})
    platform_post.refresh_from_db()
    assert "post_type" not in platform_post.platform_extra


@pytest.mark.parametrize(
    ("platform", "extra", "expected"),
    [
        ("instagram", {}, PostType.REEL),
        ("instagram", {"post_type": "reel"}, PostType.REEL),
        ("facebook", {}, PostType.VIDEO),
    ],
)
def test_single_instagram_video_resolves_to_reel(platform, extra, expected):
    assert PublishEngine._resolve_post_type(platform, extra, 1, "video") == expected


def test_reel_requires_one_video():
    provider = InstagramProvider({"ig_user_id": "123"})
    for urls in (["https://example.com/a.jpg"], ["https://example.com/a.mp4", "https://example.com/b.mp4"]):
        content = PublishContent(post_type=PostType.REEL, media_urls=urls)
        with patch.object(provider, "_create_container") as create, pytest.raises(PublishError):
            provider.publish_post("token", content)
        create.assert_not_called()


@pytest.mark.django_db
def test_preview_renders_reel_layout(client, instagram_editor):
    workspace, account = instagram_editor
    body = client.get(
        reverse("composer:preview", kwargs={"workspace_id": workspace.id}),
        {"selected_accounts": str(account.id), f"ig_format_{account.id}": "reel", "caption": "Meu reel"},
    ).content.decode()
    assert "Áudio original" in body
    assert "Enviar mensagem" not in body
