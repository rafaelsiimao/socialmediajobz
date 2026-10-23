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


def test_story_requires_exactly_one_media():
    provider = InstagramProvider({"ig_user_id": "123"})
    content = PublishContent(
        post_type=PostType.STORY, media_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"]
    )
    with patch.object(provider, "_create_container") as create, pytest.raises(PublishError):
        provider.publish_post("token", content)
    create.assert_not_called()
