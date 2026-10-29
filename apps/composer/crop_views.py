"""Non-destructive photo crops for the composer, scoped to the workspace."""

import io
import math
import uuid
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.media_library.models import MediaAsset
from apps.members.decorators import require_permission

from .views import _get_workspace


def _read_photo(asset):
    if asset.media_type != MediaAsset.MediaType.IMAGE or not asset.file:
        raise ValueError("Selecione uma foto para recortar.")
    with asset.file.open("rb") as file, Image.open(file) as image:
        if image.width * image.height > 40_000_000 or getattr(image, "is_animated", False):
            raise ValueError("Use uma foto estática com até 40 megapixels.")
        return ImageOps.exif_transpose(image).copy()


@login_required
@require_permission("create_posts")
@require_permission("upload_media")
@require_POST
def crop_media(request, workspace_id, asset_id):
    workspace = _get_workspace(request, workspace_id)
    source = get_object_or_404(MediaAsset, pk=asset_id, workspace=workspace)
    try:
        cover_id = uuid.UUID(request.POST.get("cover_asset_id", ""))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "Selecione a capa do carrossel."}, status=400)
    cover = get_object_or_404(MediaAsset, pk=cover_id, workspace=workspace)
    try:
        values = [float(request.POST.get(key, "")) for key in ("x", "y", "width", "height")]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Recorte inválido.")
        x, y, width, height = [round(value) for value in values]
        image = _read_photo(source)
        cover_image = image if cover.pk == source.pk else _read_photo(cover)
        ratio = min(1.91, max(.8, cover_image.width / cover_image.height))
        if x < 0 or y < 0 or width < 16 or height < 16:
            raise ValueError("Escolha uma área maior dentro da foto.")
        if x + width > image.width + 1 or y + height > image.height + 1:
            raise ValueError("O recorte precisa ficar dentro da foto.")
        width, height = min(width, image.width - x), min(height, image.height - y)
        if abs(width / height / ratio - 1) > .01:
            raise ValueError("O recorte precisa seguir a proporção da capa.")
        cropped = image.crop((x, y, x + width, y + height)).convert("RGBA")
        # JPEG is accepted by both Instagram publishing connectors. Composite transparency.
        result = Image.new("RGB", cropped.size, "white")
        result.paste(cropped, mask=cropped.getchannel("A"))
        result.thumbnail((1080, 1350), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        result.save(output, "JPEG", quality=92, optimize=True)
    except (ValueError, TypeError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Não foi possível abrir esta foto. Use JPG, PNG ou WebP."
        return JsonResponse({"error": message}, status=400)

    filename = f"{Path(source.filename).stem[:180]}-recorte.jpg"
    asset = MediaAsset.objects.create(
        organization=workspace.organization, workspace=workspace, uploaded_by=request.user,
        file=ContentFile(output.getvalue(), name=filename), filename=filename,
        media_type=MediaAsset.MediaType.IMAGE, mime_type="image/jpeg",
        file_size=output.tell(), width=result.width, height=result.height,
        alt_text=source.alt_text, source="composer_crop",
    )
    # Replace one thumbnail in the form; normal save/autosave attaches this new ID.
    # Do not mutate the original asset or any existing PostMedia here.
    html = render_to_string("composer/partials/media_list_pending.html", {
        "pending_assets": [asset], "workspace": workspace,
    }, request=request)
    return JsonResponse({"asset_id": str(asset.pk), "html": html})
