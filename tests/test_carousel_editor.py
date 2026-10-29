import json
import os
from pathlib import Path

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from apps.composer.models import PlatformPost, Post, PostMedia
from apps.media_library.models import MediaAsset
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def carousel(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Carrossel")
    WorkspaceMembership.objects.create(user=org_owner, workspace=workspace, workspace_role="owner")
    account = SocialAccount.objects.create(
        workspace=workspace, platform="instagram", account_name="Carrossel",
        account_platform_id="carousel", connection_status="connected",
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Carrossel de teste")
    PlatformPost.objects.create(post=post, social_account=account)
    assets = []
    for i in range(3):
        asset = MediaAsset.objects.create(
            organization=organization, workspace=workspace, uploaded_by=org_owner,
            file=f"tests/carousel-{i}.png", filename=f"carousel-{i}.png",
            media_type="image", mime_type="image/png", file_size=32,
        )
        PostMedia.objects.create(post=post, media_asset=asset, position=i)
        assets.append(str(asset.pk))
    client.force_login(org_owner)
    return workspace, account, post, assets


@pytest.mark.django_db
@pytest.mark.parametrize("remaining", [[], [2, 0]])
@pytest.mark.parametrize("endpoint", ["autosave_edit", "save_post_edit"])
def test_explicit_media_list_wins_over_stale_pending_session(client, carousel, remaining, endpoint):
    workspace, account, post, assets = carousel
    session = client.session
    session[f"pending_media_{workspace.pk}"] = assets
    session.save()
    expected = [assets[i] for i in remaining]
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}),
        {"selected_accounts": str(account.pk), "caption": post.caption,
         "media_submitted": "1", "media_ids": expected, "action": "save_draft"},
    )
    assert response.status_code in (200, 302)
    assert [str(pm.media_asset_id) for pm in post.media_attachments.all()] == expected
    reopened = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}))
    assert [str(pm.media_asset_id) for pm in reopened.context["media_attachments"]] == expected
    assert MediaAsset.objects.filter(pk__in=assets).count() == 3


@pytest.mark.django_db
def test_preview_explicit_empty_list_does_not_resurrect_saved_media(client, carousel):
    workspace, account, post, _ = carousel
    response = client.get(
        reverse("composer:preview", kwargs={"workspace_id": workspace.pk}),
        {"selected_accounts": str(account.pk), "_autosave_post_id": str(post.pk), "media_submitted": "1"},
    )
    assert response.status_code == 200
    assert response.context["media_items"] == []


@pytest.mark.django_db
def test_carousel_browser_fixture(client, carousel):
    workspace, _, post, assets = carousel
    response = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}))
    assert response.status_code == 200
    if directory := os.environ.get("CAROUSEL_BROWSER_FIXTURE_DIR"):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "carousel-editor.json").write_text(
            json.dumps({
                "html": response.content.decode(), "mediaIds": assets,
                "pendingHtml": render_to_string("composer/partials/media_list_pending.html", {
                    "workspace": workspace,
                    "pending_assets": list(MediaAsset.objects.filter(pk__in=assets).order_by("filename")),
                }),
            }), encoding="utf-8",
        )
