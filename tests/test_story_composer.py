import pytest
from django.urls import reverse

from apps.approvals.external import issue_link, preview_channels
from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def story_editor(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Stories")
    WorkspaceMembership.objects.create(user=org_owner, workspace=workspace, workspace_role="owner")
    accounts = {}
    for platform in ("instagram", "instagram_personal", "facebook"):
        accounts[platform] = SocialAccount.objects.create(
            workspace=workspace,
            platform=platform,
            account_platform_id=platform,
            account_name=platform,
            connection_status="connected",
        )
    client.force_login(org_owner)
    return workspace, accounts


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
@pytest.mark.parametrize(
    "other_platform,other_format",
    [("facebook", "feed"), ("instagram_personal", "feed"), ("instagram_personal", "reel")],
)
def test_story_cannot_be_combined_and_does_not_create_post(
    client, story_editor, endpoint, other_platform, other_format
):
    workspace, accounts = story_editor
    ig, other = accounts["instagram"], accounts[other_platform]
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": f"{ig.pk},{other.pk}",
            "action": "save_draft",
            "caption": "Preservar",
            f"ig_format_{ig.pk}": "story",
            f"ig_format_{other.pk}": other_format,
        },
    )
    assert response.status_code == 400
    assert not Post.objects.filter(workspace=workspace).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("format_value", [None, "invalid"])
def test_missing_format_still_blocks_mixing_an_existing_story(client, story_editor, org_owner, format_value):
    workspace, accounts = story_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Original")
    PlatformPost.objects.create(post=post, social_account=accounts["instagram"], platform_extra={"post_type": "story"})
    data = {
        "selected_accounts": f"{accounts['instagram'].pk},{accounts['facebook'].pk}",
        "caption": "Não salvar",
        "action": "save_draft",
    }
    if format_value is not None:
        data[f"ig_format_{accounts['instagram'].pk}"] = format_value
    response = client.post(
        reverse("composer:save_post_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}), data
    )
    assert response.status_code == 400
    post.refresh_from_db()
    assert post.caption == "Original"
    assert post.platform_posts.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("platform", ["instagram", "instagram_personal"])
def test_story_ignores_text_but_restores_it_for_feed_and_reel(story_editor, org_owner, platform):
    workspace, accounts = story_editor
    post = Post.objects.create(
        workspace=workspace, author=org_owner, caption="Legenda original", first_comment="Comentário original"
    )
    pp = PlatformPost.objects.create(
        post=post,
        social_account=accounts[platform],
        platform_extra={"post_type": "story"},
        platform_specific_caption="Legenda personalizada",
        platform_specific_first_comment="Comentário personalizado",
    )
    assert pp.effective_caption == ""
    assert pp.effective_first_comment == ""
    assert preview_channels(post)[0]["caption"] == ""
    assert preview_channels(post)[0]["first_comment"] == ""
    for fmt in ("feed", "reel"):
        pp.platform_extra = {"post_type": fmt}
        assert pp.effective_caption == "Legenda personalizada"
        assert pp.effective_first_comment == "Comentário personalizado"
    post.refresh_from_db()
    assert post.caption == "Legenda original"
    assert post.first_comment == "Comentário original"


@pytest.mark.django_db
def test_story_preview_has_no_caption_comment_or_character_limit(client, story_editor):
    workspace, accounts = story_editor
    ig = accounts["instagram"]
    response = client.get(
        reverse("composer:preview", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": str(ig.pk),
            f"ig_format_{ig.pk}": "story",
            "caption": "NÃO EXIBIR" * 1000,
            "first_comment": "COMENTÁRIO OCULTO",
        },
    )
    assert response.status_code == 200
    p = response.context["previews"][0]
    assert p["caption"] == p["first_comment"] == ""
    assert not p["is_over_limit"]
    assert "2200" not in response.content.decode()


@pytest.mark.django_db
def test_story_format_is_not_accepted_for_facebook(client, story_editor):
    workspace, accounts = story_editor
    fb = accounts["facebook"]
    response = client.post(
        reverse("composer:save_post", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": str(fb.pk),
            f"ig_format_{fb.pk}": "story",
            "action": "save_draft",
        },
    )
    assert response.status_code == 400
    assert not Post.objects.filter(workspace=workspace).exists()


@pytest.mark.django_db
def test_multiple_instagram_stories_remain_compatible(client, story_editor):
    workspace, accounts = story_editor
    ig, personal = accounts["instagram"], accounts["instagram_personal"]
    response = client.post(
        reverse("composer:save_post", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": f"{ig.pk},{personal.pk}",
            f"ig_format_{ig.pk}": "story",
            f"ig_format_{personal.pk}": "story",
            "action": "save_draft",
            "caption": "Guardada para depois",
        },
    )
    assert response.status_code == 302
    assert Post.objects.get(workspace=workspace).platform_posts.count() == 2


@pytest.mark.django_db
def test_external_approval_for_story_does_not_show_saved_text(client, story_editor, org_owner):
    workspace, accounts = story_editor
    post = Post.objects.create(
        workspace=workspace, author=org_owner, caption="LEGENDA SECRETA", first_comment="COMENTÁRIO SECRETO"
    )
    PlatformPost.objects.create(post=post, social_account=accounts["instagram"], platform_extra={"post_type": "story"})
    link, token = issue_link(post, org_owner, "Cliente", "cliente@example.com")
    client.logout()
    html = client.get(reverse("public_approval", args=[token])).content.decode()
    assert "LEGENDA SECRETA" not in html
    assert "COMENTÁRIO SECRETO" not in html


@pytest.mark.django_db
def test_editor_keeps_ordered_media_and_stored_text(client, story_editor, org_owner):
    import json
    import os
    from pathlib import Path

    from apps.composer.models import PostMedia
    from apps.media_library.models import MediaAsset

    workspace, accounts = story_editor
    post = Post.objects.create(
        workspace=workspace, author=org_owner, caption="Legenda guardada", first_comment="Comentário guardado"
    )
    PlatformPost.objects.create(post=post, social_account=accounts["instagram"])
    assets = []
    for i in range(2):
        asset = MediaAsset.objects.create(
            organization=workspace.organization,
            workspace=workspace,
            uploaded_by=org_owner,
            file=f"tests/story-{i}.png",
            filename=f"story-{i}.png",
            media_type="image",
            mime_type="image/png",
            file_size=32,
        )
        PostMedia.objects.create(post=post, media_asset=asset, position=i)
        assets.append(str(asset.pk))
    response = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}))
    assert response.status_code == 200
    assert response.context["instagram_formats_json"]
    assert [str(a.media_asset_id) for a in response.context["media_attachments"]] == assets
    assert "Legenda guardada" in response.content.decode()
    # Optional export of synthetic test data for the standalone real-browser check.
    fixture_dir = os.environ.get("STORY_BROWSER_FIXTURE_DIR")
    if fixture_dir:
        directory = Path(fixture_dir)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "story-editor.json").write_text(
            json.dumps(
                {
                    "html": response.content.decode(),
                    "mediaIds": assets,
                    "accounts": {platform: str(account.pk) for platform, account in accounts.items()},
                }
            ),
            encoding="utf-8",
        )


@pytest.mark.django_db
def test_pending_comment_task_does_not_post_to_story(story_editor, org_owner):
    from unittest.mock import patch

    from apps.publisher.engine import _post_first_comment_task

    workspace, accounts = story_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, first_comment="Não enviar")
    pp = PlatformPost.objects.create(
        post=post, social_account=accounts["instagram"], platform_extra={"post_type": "story"}
    )
    with patch("apps.publisher.engine.get_provider") as provider:
        _post_first_comment_task.now(str(pp.pk))
    provider.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
@pytest.mark.parametrize("fmt", ["feed", "reel"])
def test_post_and_reel_keep_their_text_and_other_networks(client, story_editor, endpoint, fmt):
    workspace, accounts = story_editor
    ig, fb = accounts["instagram"], accounts["facebook"]
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": f"{ig.pk},{fb.pk}",
            f"ig_format_{ig.pk}": fmt,
            "caption": "Legenda normal",
            "first_comment": "Comentário normal",
            "action": "save_draft",
        },
    )
    assert response.status_code in (200, 302)
    post = Post.objects.get(workspace=workspace)
    assert post.platform_posts.count() == 2
    for pp in post.platform_posts.all():
        assert pp.effective_caption == "Legenda normal"
        assert pp.effective_first_comment == "Comentário normal"
