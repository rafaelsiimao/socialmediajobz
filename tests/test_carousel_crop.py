import io

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image

from apps.media_library.models import MediaAsset
from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace
from tests.test_carousel_editor import carousel as carousel


@pytest.fixture
def crop_source(carousel, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    workspace, account, post, ids = carousel
    for index, size in ((0, (800, 1000)), (2, (1600, 900))):
        asset = MediaAsset.objects.get(pk=ids[index])
        image = Image.new("RGB", size, "red")
        if index == 2:
            image.paste("blue", (800, 0, 1600, 900))
        output = io.BytesIO()
        image.save(output, "PNG")
        asset.file.save(f"source-{index}.png", ContentFile(output.getvalue()), save=False)
        asset.width, asset.height = size
        asset.save()
    return workspace, account, post, ids


def crop_url(workspace, asset_id):
    return reverse("composer:crop_media", kwargs={"workspace_id": workspace.pk, "asset_id": asset_id})


@pytest.mark.django_db
def test_crop_creates_separate_file_and_preserves_original_and_other_posts(client, crop_source):
    workspace, account, post, ids = crop_source
    source = MediaAsset.objects.get(pk=ids[2])
    original_name = source.file.name
    response = client.post(crop_url(workspace, source.pk), {
        "cover_asset_id": ids[0], "x": 850, "y": 0, "width": 720, "height": 900,
    })
    assert response.status_code == 200
    data = response.json()
    result = MediaAsset.objects.get(pk=data["asset_id"])
    assert result.pk != source.pk
    assert (result.width, result.height) == (720, 900)
    assert result.mime_type == "image/jpeg"
    assert result.workspace == workspace
    with result.file.open("rb") as file:
        image = Image.open(file)
        assert image.getpixel((200, 200))[2] > 240  # User selected the right (blue) region.
    source.refresh_from_db()
    assert source.file.name == original_name
    assert (source.width, source.height) == (1600, 900)
    assert [str(pm.media_asset_id) for pm in post.media_attachments.all()] == ids
    # The editor replaces just the selected slide and persists through normal autosave.
    updated = [ids[0], ids[1], str(result.pk)]
    save = client.post(reverse("composer:autosave_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}), {
        "selected_accounts": str(account.pk), "caption": post.caption,
        "media_ids": updated, "media_submitted": "1",
    })
    assert save.status_code == 200
    reopened = client.get(reverse("composer:compose_edit", kwargs={"workspace_id": workspace.pk, "post_id": post.pk}))
    assert [str(pm.media_asset_id) for pm in reopened.context["media_attachments"]] == updated


@pytest.mark.django_db
@pytest.mark.parametrize("patch", [
    {"x": -1}, {"x": 1400}, {"width": 1600}, {"height": 0},
    {"x": "nan"}, {"x": "inf"}, {"width": "bad"},
])
def test_crop_rejects_outside_or_incorrect_ratio_without_creating_asset(client, crop_source, patch):
    workspace, _, _, ids = crop_source
    before = MediaAsset.objects.count()
    data = {"cover_asset_id": ids[0], "x": 0, "y": 0, "width": 720, "height": 900, **patch}
    assert client.post(crop_url(workspace, ids[2]), data).status_code == 400
    assert MediaAsset.objects.count() == before


@pytest.mark.django_db
@pytest.mark.parametrize("foreign", ["source", "cover"])
def test_crop_cannot_read_assets_in_another_workspace(client, crop_source, organization, foreign):
    workspace, _, _, ids = crop_source
    other = Workspace.objects.create(organization=organization, name="Outro cliente")
    asset_id = ids[2] if foreign == "source" else ids[0]
    MediaAsset.objects.filter(pk=asset_id).update(workspace=other)
    response = client.post(crop_url(workspace, ids[2]), {
        "cover_asset_id": ids[0], "x": 0, "y": 0, "width": 720, "height": 900,
    })
    assert response.status_code == 404


@pytest.mark.django_db
def test_viewer_cannot_create_crop(client, crop_source, org_owner):
    workspace, _, _, ids = crop_source
    WorkspaceMembership.objects.filter(workspace=workspace, user=org_owner).update(workspace_role="viewer")
    assert client.post(crop_url(workspace, ids[2]), {}).status_code == 403


@pytest.mark.django_db
def test_photo_crop_can_follow_video_cover(client, crop_source):
    workspace, _, _, ids = crop_source
    MediaAsset.objects.filter(pk=ids[0]).update(media_type="video", duration=30, width=1920, height=1080)
    response = client.post(crop_url(workspace, ids[2]), {
        "cover_asset_id": ids[0], "x": 0, "y": 0, "width": 1600, "height": 900,
    })
    assert response.status_code == 200
    asset = MediaAsset.objects.get(pk=response.json()["asset_id"])
    assert abs(asset.width / asset.height - 1920 / 1080) < .01
