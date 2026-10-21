"""Local upload URLs that work behind Gunicorn without exposing the media tree."""

from urllib.parse import urlencode

from django.core import signing
from django.core.files.storage import FileSystemStorage
from django.urls import reverse

MEDIA_URL_SALT = "brightbean.local-media"
MEDIA_URL_MAX_AGE = 3600


class SignedMediaStorage(FileSystemStorage):
    def url(self, name):
        token = signing.dumps(name, salt=MEDIA_URL_SALT)
        return reverse("signed_media", kwargs={"name": name}) + "?" + urlencode({"token": token})
