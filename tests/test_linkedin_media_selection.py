import json
import os
from pathlib import Path

import pytest
from django.urls import reverse

from apps.composer.models import PlatformPost, Post, PostMedia
from apps.media_library.models import MediaAsset
from apps.social_accounts.models import SocialAccount
from tests.test_story_composer import story_editor as story_editor


@pytest.fixture
def linkedin_editor(story_editor):
    workspace, accounts = story_editor
    for platform in ("linkedin_personal", "linkedin_company"):
        accounts[platform] = SocialAccount.objects.create(
            workspace=workspace,
            platform=platform,
            account_name=platform,
            account_platform_id=platform,
            connection_status="connected",
        )
    assets = [
        MediaAsset.objects.create(
            workspace=workspace,
            filename=f"{i}.{ext}",
            file=f"tests/{i}.{ext}",
            media_type=kind,
        )
        for i, (kind, ext) in enumerate([("video", "mp4"), ("image", "jpg"), ("video", "mov")])
    ]
    return workspace, accounts, assets


@pytest.mark.django_db
@pytest.mark.parametrize("platform", ["linkedin_personal", "linkedin_company"])
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
@pytest.mark.parametrize("indices", [[0, 1], [1, 0], [0, 2]])
def test_invalid_linkedin_attachments_do_not_create_post(client, linkedin_editor, platform, endpoint, indices):
    workspace, accounts, assets = linkedin_editor
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": str(accounts[platform].pk),
            "caption": "Preservar",
            "action": "add_to_queue",
            "media_submitted": "1",
            "media_ids": [str(assets[i].pk) for i in indices],
        },
    )
    assert response.status_code == 400
    assert "um vídeo" in response.json()["errors"]["ig_format"][0], response.json()
    assert not Post.objects.filter(workspace=workspace).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("source", ["saved", "session", "pending_media_ids"])
def test_invalid_selection_fallback_is_validated_without_losing_saved_data(client, linkedin_editor, org_owner, source):
    workspace, accounts, assets = linkedin_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Original")
    PlatformPost.objects.create(post=post, social_account=accounts["linkedin_company"])
    for i, asset in enumerate(assets[:2]):
        PostMedia.objects.create(post=post, media_asset=asset, position=i)
    data = {"selected_accounts": str(accounts["linkedin_company"].pk), "caption": "Não substituir"}
    kwargs = {"workspace_id": workspace.pk}
    if source == "saved":
        kwargs["post_id"] = post.pk
    elif source == "session":
        session = client.session
        session[f"pending_media_{workspace.pk}"] = [str(a.pk) for a in assets[:2]]
        session.save()
    else:
        data["pending_media_ids"] = [str(a.pk) for a in assets[:2]]
    response = client.post(
        reverse("composer:autosave_edit" if source == "saved" else "composer:autosave", kwargs=kwargs), data
    )
    assert response.status_code == 400
    post.refresh_from_db()
    assert post.caption == "Original"
    assert post.media_attachments.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("indices", [[], [0], [1]])
def test_valid_selection_can_replace_invalid_saved_attachments(client, linkedin_editor, org_owner, indices):
    workspace, accounts, assets = linkedin_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Original")
    PlatformPost.objects.create(post=post, social_account=accounts["linkedin_company"])
    for i, asset in enumerate(assets[:2]):
        PostMedia.objects.create(post=post, media_asset=asset, position=i)
    response = client.post(
        reverse("composer:autosave_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}),
        {
            "selected_accounts": str(accounts["linkedin_company"].pk),
            "caption": "Corrigido",
            "media_submitted": "1",
            "media_ids": [str(assets[i].pk) for i in indices],
        },
    )
    assert response.status_code == 200
    assert list(post.media_attachments.values_list("media_asset_id", flat=True)) == [assets[i].pk for i in indices]


@pytest.mark.django_db
def test_export_linkedin_browser_fixture(client, linkedin_editor, org_owner):
    workspace, accounts, assets = linkedin_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Teste LinkedIn")
    PlatformPost.objects.create(post=post, social_account=accounts["linkedin_company"])
    for i, asset in enumerate(assets[:2]):
        PostMedia.objects.create(post=post, media_asset=asset, position=i)
    editor = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}))
    assert editor.status_code == 200
    if directory := os.environ.get("LINKEDIN_BROWSER_FIXTURE_DIR"):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "linkedin-editor.json").write_text(
            json.dumps(
                {
                    "html": editor.content.decode(),
                    "accounts": {key: str(a.pk) for key, a in accounts.items()},
                }
            ),
            encoding="utf-8",
        )
