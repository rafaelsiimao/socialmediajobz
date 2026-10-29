from unittest.mock import MagicMock, patch

import pytest
from django.core.files.base import ContentFile

from apps.composer.models import PlatformPost, Post, PostMedia
from apps.media_library.models import MediaAsset
from apps.publisher.engine import PublishEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.exceptions import APIError
from providers.facebook import FacebookProvider


@pytest.mark.django_db
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("upload_fails", [False, True])
def test_worker_dispatches_every_saved_photo_in_order(
    organization, org_owner, settings, tmp_path, monkeypatch, override, upload_fails
):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_URL = "https://social.example"
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    workspace = Workspace.objects.create(organization=organization, name="Facebook fotos")
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="facebook",
        account_name="Página",
        account_platform_id="123",
        oauth_access_token="fake-token",
    )
    caption = "Legenda completa\n" + "Informação útil. " * 100 + "FINAL"
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
    responses = [MagicMock(json=lambda i=i: {"id": f"photo-{i}"}) for i in range(3)]
    responses.append(MagicMock(json=lambda: {"id": "123_post"}))
    if upload_fails:
        responses[1] = APIError("synthetic upload failure")
    provider = FacebookProvider({})
    with (
        patch("apps.publisher.engine.get_provider", return_value=provider),
        patch.object(provider, "_request", side_effect=responses) as request,
    ):
        result = PublishEngine()._publish_platform_post(pp)
    pp.refresh_from_db()
    if upload_fails:
        assert not result["success"]
        assert pp.status != PlatformPost.Status.PUBLISHED
        assert "synthetic upload failure" in result["error"]
        assert request.call_count == 2
        assert all(call.args[1].endswith("/photos") for call in request.call_args_list)
    else:
        assert result["success"]
        assert pp.status == PlatformPost.Status.PUBLISHED
        uploads = request.call_args_list[:-1]
        assert [call.kwargs["json"]["url"] for call in uploads] == [
            f"https://social.example{images[i].file.url}" for i in [2, 0, 1]
        ]
        final = request.call_args
        assert final.args[1].endswith("/123/feed")
        assert final.kwargs["json"]["message"] == pp.effective_caption
        assert len(final.kwargs["json"]["attached_media"]) == 3
        assert result["platform_post_id"] == "123_post"
    post.refresh_from_db()
    assert post.caption == caption
