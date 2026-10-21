import mimetypes

from django.conf import settings
from django.core import signing
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_safe

from .storage import MEDIA_URL_MAX_AGE, MEDIA_URL_SALT


@require_safe
def signed_media(request, name):
    if settings.STORAGE_BACKEND != "local":
        raise Http404
    try:
        signed_name = signing.loads(
            request.GET.get("token", ""), salt=MEDIA_URL_SALT, max_age=MEDIA_URL_MAX_AGE
        )
    except signing.BadSignature:
        return HttpResponseForbidden("Invalid or expired media link.")
    if signed_name != name:
        return HttpResponseForbidden("Invalid media link.")
    try:
        uploaded = FileSystemStorage(location=settings.MEDIA_ROOT).open(name, "rb")
    except (OSError, SuspiciousFileOperation) as exc:
        raise Http404 from exc
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    safe_inline = content_type.startswith(("image/", "video/", "audio/"))
    response = FileResponse(uploaded, content_type=content_type, as_attachment=not safe_inline)
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=300"
    return response
