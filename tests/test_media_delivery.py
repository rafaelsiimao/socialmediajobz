import time
from unittest.mock import patch
from urllib.parse import urlsplit

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client


def test_signed_media_delivery_without_debug(settings, tmp_path):
    settings.DEBUG = False
    settings.MEDIA_ROOT = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "apps.common.storage.SignedMediaStorage"},
    }
    name = default_storage.save("uploads/test.png", ContentFile(b"image bytes"))
    url = default_storage.url(name)
    client = Client()
    response = client.get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"image bytes"
    assert client.get(urlsplit(url).path).status_code == 403
    assert client.get(url + "tampered").status_code == 403
    assert client.get(url.replace("test.png", "another.png")).status_code == 403
    with patch("django.core.signing.time.time", return_value=time.time() + 3601):
        assert client.get(url).status_code == 403
