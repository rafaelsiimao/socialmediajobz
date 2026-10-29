import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from apps.composer.models import PlatformPost, Post, PostMedia
from apps.media_library.models import MediaAsset
from providers.exceptions import PublishError
from providers.instagram import InstagramProvider
from providers.instagram_personal import InstagramPersonalProvider
from providers.types import PostType, PublishContent, PublishResult
from tests.test_story_composer import story_editor as story_editor


@pytest.fixture
def mixed_assets(story_editor, org_owner):
    workspace, _ = story_editor
    assets = []
    for i, media_type in enumerate(["image", "video", "image"]):
        extension = "mp4" if media_type == "video" else "jpg"
        assets.append(
            MediaAsset.objects.create(
                workspace=workspace,
                organization=workspace.organization,
                uploaded_by=org_owner,
                file=f"tests/mixed-{i}.{extension}",
                filename=f"mixed-{i}.{extension}",
                media_type=media_type,
                duration=30 if media_type == "video" else 0,
                width=1920 if media_type == "video" else 1080,
                height=1080 if media_type == "video" else 1350,
            )
        )
    return assets


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
@pytest.mark.parametrize("platform", ["instagram", "instagram_personal"])
def test_mixed_feed_saves_in_selected_order(client, story_editor, mixed_assets, endpoint, platform):
    workspace, accounts = story_editor
    ordered = [mixed_assets[1], mixed_assets[0], mixed_assets[2]]
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": str(accounts[platform].pk),
            "action": "save_draft",
            "caption": "Carrossel misto",
            "media_submitted": "1",
            "media_ids": [str(asset.pk) for asset in ordered],
        },
    )
    assert response.status_code in (200, 302)
    post = Post.objects.get(workspace=workspace)
    assert list(post.media_attachments.values_list("media_asset_id", flat=True)) == [asset.pk for asset in ordered]


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["save_post", "autosave"])
@pytest.mark.parametrize("invalid", ["long_video", "too_many", "other_network", "unsupported_video"])
def test_invalid_mixed_feed_is_rejected_before_post_changes(client, story_editor, mixed_assets, endpoint, invalid):
    workspace, accounts = story_editor
    ids = [str(asset.pk) for asset in mixed_assets]
    selected = str(accounts["instagram"].pk)
    if invalid == "long_video":
        mixed_assets[1].duration = 61
        mixed_assets[1].save()
    elif invalid == "too_many":
        for i in range(8):
            asset = MediaAsset.objects.create(
                workspace=workspace, file=f"tests/extra-{i}.jpg", filename=f"extra-{i}.jpg", media_type="image"
            )
            ids.append(str(asset.pk))
    elif invalid == "other_network":
        selected += f",{accounts['facebook'].pk}"
    elif invalid == "unsupported_video":
        mixed_assets[1].file = "tests/unsupported.webm"
        mixed_assets[1].save()
    response = client.post(
        reverse(f"composer:{endpoint}", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": selected,
            "action": "save_draft",
            "caption": "Não salvar",
            "media_submitted": "1",
            "media_ids": ids,
        },
    )
    assert response.status_code == 400
    assert not Post.objects.filter(workspace=workspace).exists()


@pytest.mark.parametrize("provider_class", [InstagramProvider, InstagramPersonalProvider])
def test_mixed_carousel_creates_image_and_video_children_in_order(provider_class):
    provider = provider_class({"ig_user_id": "123"})
    urls = [
        "https://example.com/1.jpg",
        "https://example.com/2.mp4?sig=1",
        "https://example.com/3.mov",
        "https://example.com/4.jpg",
    ]
    with (
        patch.object(provider, "_create_container", side_effect=["c1", "c2", "c3", "c4", "parent"]) as create,
        patch.object(provider, "_wait_for_container"),
        patch.object(provider, "_publish_container", return_value=PublishResult("published")),
    ):
        provider.publish_post(
            "fake-token",
            PublishContent(
                text="Legenda",
                media_urls=urls,
                post_type=PostType.CAROUSEL,
                extra={"ig_user_id": "123", "collaborators": ["partner"]},
            ),
        )
    payloads = [call.args[-1] for call in create.call_args_list]
    assert payloads[0] == {"is_carousel_item": True, "image_url": urls[0]}
    assert payloads[1] == {"is_carousel_item": True, "media_type": "VIDEO", "video_url": urls[1]}
    assert payloads[2]["video_url"] == urls[2]
    assert payloads[3]["image_url"] == urls[3]
    assert payloads[4] == {
        "media_type": "CAROUSEL",
        "children": "c1,c2,c3,c4",
        "caption": "Legenda",
        "collaborators": ["partner"],
    }


@pytest.mark.parametrize("provider_class", [InstagramProvider, InstagramPersonalProvider])
@pytest.mark.parametrize("count", [1, 11])
def test_provider_rejects_invalid_carousel_size_before_api(provider_class, count):
    provider = provider_class({"ig_user_id": "123"})
    with (
        patch.object(provider, "_create_container") as create,
        patch.object(provider, "_request", side_effect=AssertionError("No real API in tests")),
        pytest.raises(PublishError),
    ):
        provider.publish_post(
            "fake-token",
            PublishContent(
                media_urls=[f"https://example.com/{i}.jpg" for i in range(count)],
                post_type=PostType.CAROUSEL,
                extra={"ig_user_id": "123"},
            ),
        )
    create.assert_not_called()


@pytest.mark.django_db
def test_strict_validation_reads_server_metadata_and_rejects_unknown_or_long(mixed_assets):
    from apps.composer.instagram_media import validate_carousel_assets

    video = mixed_assets[1]
    for duration in (0, 61, 30):
        video.duration = 0
        with patch(
            "apps.composer.instagram_media.extract_video_metadata",
            return_value={"duration_seconds": duration, "width": 1920, "height": 1080},
        ):
            if duration == 30:
                validate_carousel_assets(mixed_assets, strict=True, local_files=["a.jpg", "b.mp4", "c.jpg"])
                assert video.duration == 30
            else:
                with pytest.raises(ValueError):
                    validate_carousel_assets(mixed_assets, strict=True, local_files=["a.jpg", "b.mp4", "c.jpg"])


@pytest.mark.django_db
def test_upload_records_video_metadata(client, story_editor, settings, tmp_path, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    workspace, _ = story_editor
    with patch(
        "apps.composer.instagram_media.extract_video_metadata",
        return_value={"duration_seconds": 25, "width": 1920, "height": 1080},
    ):
        response = client.post(
            reverse("composer:upload_media", kwargs={"workspace_id": workspace.pk}),
            {
                "file": SimpleUploadedFile("test.mp4", b"synthetic", content_type="video/mp4"),
                "inspect_video": "1",
            },
        )
    assert response.status_code == 200
    asset = MediaAsset.objects.get(workspace=workspace)
    assert (asset.duration, asset.width, asset.height) == (25, 1920, 1080)
    assert 'data-duration="25.0"' in response.content.decode()


@pytest.mark.django_db
def test_mixed_preview_and_browser_fixture(client, story_editor, mixed_assets, org_owner):
    workspace, accounts = story_editor
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Mistura de fotos e vídeos")
    PlatformPost.objects.create(post=post, social_account=accounts["instagram"])
    for index, asset in enumerate(mixed_assets):
        PostMedia.objects.create(post=post, media_asset=asset, position=index)
    ids = [str(a.pk) for a in mixed_assets]
    preview = client.get(
        reverse("composer:preview", kwargs={"workspace_id": workspace.pk}),
        {
            "selected_accounts": str(accounts["instagram"].pk),
            "media_ids": ids,
            "media_submitted": "1",
        },
    )
    html = preview.content.decode()
    assert 'aria-label="Vídeo do carrossel"' in html
    assert "controls playsinline" in html
    assert "?.pause()" in html
    editor = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}))
    if directory := os.environ.get("MIXED_BROWSER_FIXTURE_DIR"):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mixed-editor.json").write_text(
            json.dumps(
                {
                    "html": editor.content.decode(),
                    "preview": html,
                    "mediaIds": ids,
                    "accounts": {key: str(value.pk) for key, value in accounts.items()},
                    "thumbs": [
                        render_to_string(
                            "composer/partials/media_list_pending.html",
                            {"workspace": workspace, "pending_assets": [asset]},
                        )
                        for asset in mixed_assets
                    ],
                }
            ),
            encoding="utf-8",
        )


@pytest.mark.django_db
@pytest.mark.parametrize("platform", ["instagram", "instagram_personal"])
@pytest.mark.parametrize("duration", [0, 61])
def test_worker_rejects_invalid_duration_before_provider_api(
    story_editor, mixed_assets, org_owner, settings, tmp_path, monkeypatch, platform, duration
):
    from unittest.mock import MagicMock

    from django.core.files.base import ContentFile

    from apps.publisher.engine import PublishEngine

    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    workspace, accounts = story_editor
    post = Post.objects.create(workspace=workspace, author=org_owner)
    pp = PlatformPost.objects.create(post=post, social_account=accounts[platform])
    for index, asset in enumerate(mixed_assets):
        asset.file.save(asset.filename, ContentFile(b"synthetic"), save=False)
        if asset.is_video:
            asset.duration = duration
        asset.save()
        PostMedia.objects.create(post=post, media_asset=asset, position=index)
    provider = MagicMock()
    provider.supported_post_types = [PostType.IMAGE, PostType.CAROUSEL, PostType.REEL, PostType.STORY]
    with (
        patch("apps.publisher.engine.get_provider", return_value=provider),
        patch("apps.composer.instagram_media.extract_video_metadata", return_value={}),
        pytest.raises(ValueError),
    ):
        PublishEngine()._dispatch_to_provider(pp)
    provider.publish_post.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("duration", [30, 61])
def test_real_ffprobe_validates_synthetic_video(mixed_assets, tmp_path, duration):
    import shutil
    import subprocess

    from apps.composer.instagram_media import validate_carousel_assets

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe are needed for the synthetic video integration check")
    path = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=160x90:r=2",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    mixed_assets[1].duration = 0
    if duration > 60:
        with pytest.raises(ValueError, match="60"):
            validate_carousel_assets(mixed_assets, strict=True, local_files=["a.jpg", str(path), "c.jpg"])
    else:
        validate_carousel_assets(mixed_assets, strict=True, local_files=["a.jpg", str(path), "c.jpg"])
        assert mixed_assets[1].duration == 30


@pytest.mark.parametrize(
    "rotation,expected", [(0, (1920, 1080)), (90, (1080, 1920)), (-90, (1080, 1920)), (180, (1920, 1080))]
)
def test_video_dimensions_follow_display_rotation(rotation, expected):
    from unittest.mock import MagicMock

    from apps.media_library.services import extract_video_metadata

    output = {
        "format": {"duration": "30"},
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "side_data_list": [{"rotation": rotation}]}],
    }
    with patch(
        "apps.media_library.services.subprocess.run", return_value=MagicMock(returncode=0, stdout=json.dumps(output))
    ):
        metadata = extract_video_metadata("synthetic.mp4")
    assert (metadata["width"], metadata["height"]) == expected
