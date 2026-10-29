from unittest.mock import MagicMock, patch

import pytest

from providers.exceptions import APIError, PublishError
from providers.facebook import BASE_URL, FacebookProvider
from providers.types import PostType, PublishContent


def content(urls, post_type=PostType.IMAGE):
    return PublishContent(
        text="Legenda completa (ação)\n" + "Todas as fotos na ordem. " * 100,
        post_type=post_type,
        media_urls=urls,
        extra={"page_id": "page-1"},
    )


@pytest.mark.parametrize("count", [2, 3, 10])
@pytest.mark.parametrize("post_type", [PostType.IMAGE, PostType.CAROUSEL])
def test_publishes_one_feed_post_with_all_photos_in_order(count, post_type):
    provider = FacebookProvider({})
    post = content([f"https://media.example/{i}.jpg" for i in range(count)], post_type)
    responses = [MagicMock(json=lambda i=i: {"id": f"photo-{i}"}) for i in range(count)]
    responses.append(MagicMock(json=lambda: {"id": "page-1_post-1"}))
    with patch.object(provider, "_request", side_effect=responses) as request:
        result = provider.publish_post("fake-token", post)
    assert request.call_count == count + 1
    for i, call in enumerate(request.call_args_list[:-1]):
        assert call.args == ("POST", f"{BASE_URL}/page-1/photos")
        assert call.kwargs["json"] == {"url": post.media_urls[i], "published": False}
    final = request.call_args
    assert final.args == ("POST", f"{BASE_URL}/page-1/feed")
    assert final.kwargs["json"] == {
        "message": post.text,
        "attached_media": [{"media_fbid": f"photo-{i}"} for i in range(count)],
    }
    assert result.platform_post_id == "page-1_post-1"
    assert result.url == "https://www.facebook.com/page-1_post-1"


def test_failed_photo_upload_never_creates_partial_feed_post():
    provider = FacebookProvider({})
    with (
        patch.object(
            provider, "_request", side_effect=[MagicMock(json=lambda: {"id": "photo-1"}), APIError("upload failed")]
        ) as request,
        pytest.raises(APIError, match="upload failed"),
    ):
        provider.publish_post("fake-token", content(["https://media.example/1.jpg", "https://media.example/2.jpg"]))
    assert request.call_count == 2
    assert all(call.args[1].endswith("/photos") for call in request.call_args_list)
    assert all(call.kwargs["json"]["published"] is False for call in request.call_args_list)


def test_missing_uploaded_photo_id_stops_before_feed_post():
    provider = FacebookProvider({})
    with (
        patch.object(provider, "_request", return_value=MagicMock(json=lambda: {})) as request,
        pytest.raises(PublishError),
    ):
        provider.publish_post("fake-token", content(["https://media.example/1.jpg", "https://media.example/2.jpg"]))
    assert request.call_count == 1


@pytest.mark.parametrize("final_response", [{}, APIError("feed failed")])
def test_feed_failure_is_never_reported_as_success(final_response):
    provider = FacebookProvider({})
    final = final_response if isinstance(final_response, Exception) else MagicMock(json=lambda: final_response)
    with (
        patch.object(
            provider,
            "_request",
            side_effect=[MagicMock(json=lambda: {"id": "1"}), MagicMock(json=lambda: {"id": "2"}), final],
        ),
        pytest.raises((PublishError, APIError)),
    ):
        provider.publish_post("fake-token", content(["https://media.example/1.jpg", "https://media.example/2.jpg"]))


@pytest.mark.parametrize(
    "urls,post_type",
    [
        (["1.jpg", "2.mp4?signature=fake"], PostType.IMAGE),
        (["1.mov", "2.jpg"], PostType.VIDEO),
        (["1.mp4", "2.mp4"], PostType.VIDEO),
    ],
)
def test_multiple_media_with_video_is_rejected_before_publishing(urls, post_type):
    provider = FacebookProvider({})
    with patch.object(provider, "_request") as request, pytest.raises(PublishError):
        provider.publish_post("fake-token", content([f"https://media.example/{url}" for url in urls], post_type))
    request.assert_not_called()


def test_single_photo_preserves_feed_post_id_for_metrics():
    provider = FacebookProvider({})
    with patch.object(
        provider, "_request", return_value=MagicMock(json=lambda: {"id": "photo-1", "post_id": "page-1_post-1"})
    ) as request:
        result = provider.publish_post("fake-token", content(["https://media.example/1.jpg"]))
    assert request.call_count == 1
    assert "published" not in request.call_args.kwargs["json"]
    assert result.platform_post_id == "page-1_post-1"


def test_single_video_stays_on_video_endpoint():
    provider = FacebookProvider({})
    with patch.object(provider, "_request", return_value=MagicMock(json=lambda: {"id": "video-1"})) as request:
        post = content(["https://media.example/1.mp4"], PostType.VIDEO)
        provider.publish_post("fake-token", post)
    assert request.call_args.args[1] == f"{BASE_URL}/page-1/videos"
    assert request.call_args.kwargs["json"] == {"file_url": post.media_urls[0], "description": post.text}
