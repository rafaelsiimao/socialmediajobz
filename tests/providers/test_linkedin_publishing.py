import re
from unittest.mock import MagicMock, patch

import pytest

from providers.exceptions import APIError, PublishError
from providers.linkedin_company import LinkedInCompanyProvider
from providers.linkedin_personal import LinkedInPersonalProvider
from providers.types import PostType, PublishContent


@pytest.fixture(params=[LinkedInCompanyProvider, LinkedInPersonalProvider])
def linkedin(request):
    return request.param({})


@pytest.mark.parametrize("post_type", [PostType.IMAGE, PostType.CAROUSEL])
@pytest.mark.parametrize("local", [True, False])
@pytest.mark.parametrize("count", [2, 3, 20])
def test_all_photos_are_uploaded_in_order_with_complete_caption(linkedin, post_type, local, count):
    sources = (
        [f"/tmp/slide-{i}.jpg" for i in range(count)]
        if local
        else [f"https://example.com/slide-{i}.jpg" for i in range(count)]
    )
    caption = (
        "Legenda completa (sem cortes).\n\n* Primeiro ponto\n* Segundo ponto @contato #Jobz\n" + "Conteúdo útil. " * 120
    )
    content = PublishContent(
        text=caption,
        post_type=post_type,
        media_files=sources if local else [],
        media_urls=["https://example.com/ignored.jpg"] if local else sources,
        extra={"author": "urn:li:organization:123"},
    )
    responses = [
        MagicMock(
            json=lambda i=i: {"value": {"uploadUrl": f"https://upload.example/{i}", "image": f"urn:li:image:{i}"}}
        )
        for i in range(count)
    ]
    responses.append(MagicMock(headers={"x-restli-id": "urn:li:share:456"}))
    with (
        patch.object(linkedin, "_request", side_effect=responses) as request,
        patch.object(linkedin, "_upload_binary") as upload,
    ):
        result = linkedin.publish_post("fake-token", content)
    assert upload.call_count == count
    assert [call.args[2] for call in upload.call_args_list] == sources
    body = request.call_args.kwargs["json"]
    assert body["content"] == {"multiImage": {"images": [{"id": f"urn:li:image:{i}"} for i in range(count)]}}
    assert re.sub(r"\\(.)", r"\1", body["commentary"]) == caption
    assert body["commentary"] != caption
    assert result.platform_post_id == "urn:li:share:456"


def test_single_image_keeps_single_media_shape(linkedin):
    responses = [
        MagicMock(json=lambda: {"value": {"uploadUrl": "https://upload.example/1", "image": "urn:li:image:1"}}),
        MagicMock(headers={"x-restli-id": "urn:li:share:1"}),
    ]
    with patch.object(linkedin, "_request", side_effect=responses) as request, patch.object(linkedin, "_upload_binary"):
        linkedin.publish_post(
            "fake-token",
            PublishContent(
                text="Foto",
                post_type=PostType.IMAGE,
                media_urls=["https://example.com/1.jpg"],
                extra={"author": "urn:li:person:1"},
            ),
        )
    assert request.call_args.kwargs["json"]["content"] == {"media": {"id": "urn:li:image:1"}}


@pytest.mark.parametrize(
    "text",
    [
        "Antes (detalhes importantes) e o FINAL.",
        "[Título] {texto} | @nome <empresa> #Jobz *lista* _itálico_ ~risco~ \\ fim",
        "🚀 Ação, gestão e carreira\n\nhttps://jobz.com.br/vaga_(teste)?id=1\nFINAL",
        "A" * 3000,
    ],
)
def test_commentary_escapes_little_text_without_losing_characters(linkedin, text):
    body = linkedin._build_post_body("urn:li:person:1", text)
    assert re.sub(r"\\(.)", r"\1", body["commentary"]) == text
    if "(" in text:
        assert "\\(" in body["commentary"]


@pytest.mark.parametrize("count", [21])
def test_too_many_images_fails_before_upload(linkedin, count):
    with (
        patch.object(linkedin, "_request") as request,
        patch.object(linkedin, "_upload_binary") as upload,
        pytest.raises(PublishError),
    ):
        linkedin.publish_post(
            "fake-token",
            PublishContent(
                post_type=PostType.IMAGE,
                media_urls=[f"https://example.com/{i}.jpg" for i in range(count)],
                extra={"author": "urn:li:person:1"},
            ),
        )
    request.assert_not_called()
    upload.assert_not_called()


def test_failed_middle_upload_never_publishes_partial_carousel(linkedin):
    init = [
        MagicMock(
            json=lambda i=i: {"value": {"uploadUrl": f"https://upload.example/{i}", "image": f"urn:li:image:{i}"}}
        )
        for i in range(2)
    ]
    with (
        patch.object(linkedin, "_request", side_effect=init) as request,
        patch.object(linkedin, "_upload_binary", side_effect=[None, APIError("upload failed", status_code=500)]),
        pytest.raises(APIError),
    ):
        linkedin.publish_post(
            "fake-token",
            PublishContent(
                post_type=PostType.IMAGE,
                media_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
                extra={"author": "urn:li:person:1"},
            ),
        )
    assert all(call.args[1].endswith("/rest/images") for call in request.call_args_list)


def test_mixed_image_video_is_not_uploaded_as_a_photo_carousel(linkedin):
    with patch.object(linkedin, "_request") as request, pytest.raises(PublishError):
        linkedin.publish_post(
            "fake-token",
            PublishContent(
                post_type=PostType.IMAGE,
                media_urls=["https://example.com/1.jpg", "https://example.com/2.mp4?signature=mock"],
                extra={"author": "urn:li:person:1"},
            ),
        )
    request.assert_not_called()


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("tail", ["photo.jpg", "second.mp4"])
@pytest.mark.parametrize("author", [None, "urn:li:organization:123"])
def test_video_first_never_drops_remaining_attachments(linkedin, local, tail, author):
    sources = ["https://example.com/first.mp4", f"https://example.com/{tail}"]
    with (
        patch.object(linkedin, "_request") as request,
        patch.object(linkedin, "_upload_binary") as upload,
        patch.object(linkedin, "get_profile") as profile,
        pytest.raises(PublishError, match="um vídeo"),
    ):
        linkedin.publish_post(
            "fake-token",
            PublishContent(
                post_type=PostType.VIDEO,
                media_files=sources if local else [],
                media_urls=sources,
                extra={"author": author} if author else {},
            ),
        )
    request.assert_not_called()
    upload.assert_not_called()
    profile.assert_not_called()


def test_single_video_still_uploads_with_complete_caption(linkedin):
    responses = [
        MagicMock(json=lambda: {"value": {"uploadUrl": "https://upload.example/video", "video": "urn:li:video:1"}}),
        MagicMock(headers={"x-restli-id": "urn:li:share:123"}),
    ]
    with (
        patch.object(linkedin, "_request", side_effect=responses) as request,
        patch.object(linkedin, "_upload_binary") as upload,
    ):
        linkedin.publish_post(
            "fake-token",
            PublishContent(
                text="Legenda completa",
                post_type=PostType.VIDEO,
                media_urls=["https://example.com/video.mp4"],
                extra={"author": "urn:li:organization:123"},
            ),
        )
    upload.assert_called_once()
    assert request.call_args.kwargs["json"]["content"] == {"media": {"id": "urn:li:video:1"}}
    assert request.call_args.kwargs["json"]["commentary"] == "Legenda completa"
