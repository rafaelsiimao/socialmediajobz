import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.base import ContentFile

from apps.composer.models import PlatformPost, Post, PostMedia
from apps.media_library.models import MediaAsset
from apps.publisher.engine import PublishEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.linkedin_company import LinkedInCompanyProvider
from providers.linkedin_personal import LinkedInPersonalProvider


@pytest.mark.django_db
@pytest.mark.parametrize("override", [False, True])
def test_worker_sends_all_saved_photos_and_complete_effective_caption(
    organization, org_owner, settings, tmp_path, monkeypatch, override
):
    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    workspace = Workspace.objects.create(organization=organization, name="Publicação Company")
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_company",
        account_name="Company",
        account_platform_id="123",
        oauth_access_token="fake-token",
    )
    caption = (
        "Gestão (completa) e carreira.\n\n* Informação importante\n"
        + "Toda a legenda precisa chegar. " * 70
        + "\nFINAL #Jobz"
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, caption=caption)
    pp = PlatformPost.objects.create(
        post=post,
        social_account=account,
        platform_specific_caption=f"Personalizada: {caption}" if override else None,
    )
    images = [
        MediaAsset.objects.create(
            workspace=workspace,
            organization=organization,
            uploaded_by=org_owner,
            file=ContentFile(f"synthetic-{i}".encode(), name=f"slide-{i}.jpg"),
            filename=f"slide-{i}.jpg",
            media_type="image",
        )
        for i in range(3)
    ]
    for position, index in enumerate([2, 0, 1]):
        PostMedia.objects.create(post=post, media_asset=images[index], position=position)
    uploaded = []
    provider = LinkedInCompanyProvider({})
    responses = [
        MagicMock(
            json=lambda i=i: {"value": {"uploadUrl": f"https://upload.example/{i}", "image": f"urn:li:image:{i}"}}
        )
        for i in range(3)
    ]
    responses.append(MagicMock(headers={"x-restli-id": "urn:li:share:456"}))
    with (
        patch("apps.publisher.engine.get_provider", return_value=provider),
        patch.object(provider, "_request", side_effect=responses) as request,
        patch.object(
            provider,
            "_upload_binary",
            side_effect=lambda token, url, source: uploaded.append(Path(source).read_bytes()),
        ),
    ):
        result = PublishEngine()._dispatch_to_provider(pp)
    assert result["success"]
    assert uploaded == [b"synthetic-2", b"synthetic-0", b"synthetic-1"]
    body = request.call_args.kwargs["json"]
    assert len(body["content"]["multiImage"]["images"]) == 3
    assert body["author"] == "urn:li:organization:123"
    assert re.sub(r"\\(.)", r"\1", body["commentary"]) == pp.effective_caption
    post.refresh_from_db()
    assert post.caption == caption


@pytest.mark.django_db
@pytest.mark.parametrize(
    "platform,provider_class",
    [
        ("linkedin_company", LinkedInCompanyProvider),
        ("linkedin_personal", LinkedInPersonalProvider),
    ],
)
@pytest.mark.parametrize("second_kind", ["image", "video"])
def test_worker_rejects_saved_video_with_other_media_before_any_api(
    organization,
    org_owner,
    settings,
    tmp_path,
    monkeypatch,
    platform,
    provider_class,
    second_kind,
):
    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    workspace = Workspace.objects.create(organization=organization, name="LinkedIn inválido")
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform=platform,
        account_name="LinkedIn",
        account_platform_id="123",
        oauth_access_token="fake-token",
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Preservar legenda")
    pp = PlatformPost.objects.create(post=post, social_account=account)
    for index, kind in enumerate(["video", second_kind]):
        extension = "mp4" if kind == "video" else "jpg"
        asset = MediaAsset.objects.create(
            workspace=workspace,
            file=ContentFile(b"synthetic", name=f"{index}.{extension}"),
            filename=f"{index}.{extension}",
            media_type=kind,
        )
        PostMedia.objects.create(post=post, media_asset=asset, position=index)
    provider = provider_class({})
    with (
        patch("apps.publisher.engine.get_provider", return_value=provider),
        patch.object(provider, "_request") as request,
        patch.object(provider, "_upload_binary") as upload,
        patch.object(provider, "get_profile") as profile,
    ):
        result = PublishEngine()._publish_platform_post(pp)
    assert not result["success"]
    assert "um vídeo" in result["error"]
    pp.refresh_from_db()
    assert pp.status != PlatformPost.Status.PUBLISHED
    assert post.media_attachments.count() == 2
    request.assert_not_called()
    upload.assert_not_called()
    profile.assert_not_called()
