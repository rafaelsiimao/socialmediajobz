from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def test_local_upload_can_be_saved_and_read(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    name = default_storage.save("uploads/example.txt", ContentFile(b"upload regression"))
    assert default_storage.exists(name)
    with default_storage.open(name, "rb") as uploaded:
        assert uploaded.read() == b"upload regression"
    assert default_storage.url(name).endswith("/uploads/example.txt")
