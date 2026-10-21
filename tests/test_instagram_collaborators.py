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
    workspace = Workspace.objects.create(organization=organization, name="Collaboration workspace")
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
def test_collaborators_persist_and_reload(client, instagram_editor, endpoint):
    workspace, account = instagram_editor
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.id}),
        {
            "caption": "Collaboration draft",
            "action": "save_draft",
            "selected_accounts": str(account.id),
            f"ig_collaborators_{account.id}": "@Parceiro, outro.perfil, parceiro",
        },
    )
    assert response.status_code in (200, 204, 302)
    post = Post.objects.get(workspace=workspace)
    assert post.platform_posts.get().platform_extra["collaborators"] == ["parceiro", "outro.perfil"]
    editor = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id}))
    assert f'name="ig_collaborators_{account.id}"'.encode() in editor.content
    assert b'value="parceiro, outro.perfil"' in editor.content


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
@pytest.mark.parametrize("value", ["one,two,three,four", "https://instagram.com/partner", "invalid!name"])
def test_invalid_collaborators_do_not_create_draft(client, instagram_editor, endpoint, value):
    workspace, account = instagram_editor
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.id}),
        {"caption": "Invalid draft", "selected_accounts": str(account.id), f"ig_collaborators_{account.id}": value},
    )
    assert response.status_code == 400
    assert "collaborators" in response.json()["errors"]
    assert not Post.objects.filter(workspace=workspace).exists()


@pytest.mark.django_db
def test_collaborators_can_be_removed_without_losing_other_extras(client, instagram_editor, org_owner):
    workspace, account = instagram_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Draft")
    platform_post = post.platform_posts.create(
        social_account=account, platform_extra={"collaborators": ["partner"], "post_type": "image"}
    )
    response = client.post(
        reverse("composer:save_post_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id}),
        {
            "caption": "Draft",
            "action": "save_draft",
            "selected_accounts": str(account.id),
            f"ig_collaborators_{account.id}": "",
        },
    )
    assert response.status_code == 302
    platform_post.refresh_from_db()
    assert platform_post.platform_extra.get("collaborators", []) == []
    assert platform_post.platform_extra["post_type"] == "image"


@pytest.mark.parametrize("post_type", [PostType.IMAGE, PostType.CAROUSEL, PostType.REEL])
def test_publish_sends_collaborators_only_on_parent_container(post_type):
    provider = InstagramProvider({"ig_user_id": "123"})
    content = PublishContent(
        text="Collaboration",
        post_type=post_type,
        media_urls=["https://example.com/one.jpg", "https://example.com/two.jpg"],
        extra={"collaborators": ["@Partner", "other"]},
    )
    with (
        patch.object(provider, "_create_container", return_value="container") as create,
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", return_value=PublishResult("published")),
    ):
        provider.publish_post("test-token", content)
    payloads = [call.args[2] for call in create.call_args_list]
    assert payloads[-1]["collaborators"] == ["partner", "other"]
    assert all("collaborators" not in payload for payload in payloads[:-1])


def test_story_collaboration_is_rejected_before_api_calls():
    provider = InstagramProvider({"ig_user_id": "123"})
    content = PublishContent(
        post_type=PostType.STORY, media_urls=["https://example.com/image.jpg"], extra={"collaborators": ["partner"]}
    )
    with patch.object(provider, "_create_container") as create, pytest.raises(PublishError):
        provider.publish_post("test-token", content)
    create.assert_not_called()


@pytest.mark.django_db
def test_approval_preserves_collaborators_and_version_history(client, instagram_editor):
    workspace, account = instagram_editor
    response = client.post(
        reverse("composer:save_post", kwargs={"workspace_id": workspace.id}),
        {
            "caption": "For internal approval",
            "action": "submit_for_approval",
            "selected_accounts": str(account.id),
            f"ig_collaborators_{account.id}": "@partner",
        },
    )
    assert response.status_code == 302
    post = Post.objects.get(workspace=workspace)
    platform_post = post.platform_posts.get()
    assert platform_post.status == "pending_review"
    assert platform_post.platform_extra["collaborators"] == ["partner"]
    assert post.versions.first().snapshot["platform_posts"][0]["platform_extra"]["collaborators"] == ["partner"]


def test_publish_without_collaborators_keeps_existing_payload():
    provider = InstagramProvider({"ig_user_id": "123"})
    content = PublishContent(post_type=PostType.IMAGE, media_urls=["https://example.com/image.jpg"])
    with (
        patch.object(provider, "_create_container", return_value="container") as create,
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", return_value=PublishResult("published")),
    ):
        provider.publish_post("test-token", content)
    assert create.call_args.args[2] == {"image_url": "https://example.com/image.jpg"}


@pytest.mark.parametrize("platform,expected", [("instagram", PostType.REEL), ("facebook", PostType.VIDEO)])
def test_collaboration_video_is_resolved_as_instagram_reel(platform, expected):
    result = PublishEngine()._resolve_post_type(
        platform=platform, platform_extra={"collaborators": ["partner"]}, media_count=1, first_media_type="video"
    )
    assert result == expected
