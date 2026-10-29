"""Instagram feed carousel validation; keep Reel/Story flows separate."""

import math
import os
import tempfile
import uuid

from apps.media_library.models import MediaAsset
from apps.media_library.services import extract_video_metadata

MAX_CAROUSEL_ITEMS = 10
MAX_CAROUSEL_VIDEO_SECONDS = 60
MIXED_SELECTION_ERROR = "Para usar fotos e vídeos no mesmo carrossel, selecione apenas Instagram no formato Post."


def populate_video_metadata(asset, local_path=None):
    """Read trusted metadata using ffprobe, supporting local and remote storage."""
    if asset.duration > 0 and asset.width > 0 and asset.height > 0:
        return
    temporary = None
    try:
        if local_path is None:
            with tempfile.NamedTemporaryFile(suffix=f".{asset.file_extension}", delete=False) as target:
                temporary = target.name
                with asset.file.open("rb") as source:
                    for chunk in iter(lambda: source.read(8192), b""):
                        target.write(chunk)
            local_path = temporary
        metadata = extract_video_metadata(local_path)
        updates = []
        for field, key in (("duration", "duration_seconds"), ("width", "width"), ("height", "height")):
            value = metadata.get(key)
            if value is not None and math.isfinite(float(value)) and float(value) > 0:
                setattr(asset, field, float(value) if field == "duration" else int(value))
                updates.append(field)
        if updates:
            asset.save(update_fields=[*updates, "updated_at"])
    except (OSError, ValueError, TypeError):
        # Draft/upload may continue; strict publication refuses an unknown duration.
        pass
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def validate_carousel_assets(assets, *, strict=False, local_files=None):
    if len(assets) > MAX_CAROUSEL_ITEMS:
        raise ValueError("O carrossel do Instagram aceita até 10 fotos e vídeos no total.")
    if len(assets) < 2:
        return
    for index, asset in enumerate(assets):
        if asset.media_type not in ("image", "gif", "video"):
            raise ValueError("O carrossel aceita somente fotos e vídeos.")
        if not asset.is_video:
            continue
        if not str(asset.file.name).lower().endswith((".mp4", ".mov")):
            raise ValueError(f"Use MP4 ou MOV para o vídeo {asset.filename}.")
        if strict and (not asset.duration or not math.isfinite(asset.duration)):
            populate_video_metadata(asset, local_files[index] if local_files else None)
        if not asset.duration or not math.isfinite(asset.duration):
            if strict:
                raise ValueError(
                    f"Não foi possível conferir a duração de {asset.filename}. Reenvie o vídeo antes de publicar."
                )
        elif asset.duration > MAX_CAROUSEL_VIDEO_SECONDS:
            raise ValueError(
                f"O vídeo {asset.filename} tem mais de 60 segundos. Cada vídeo do carrossel aceita até 60 s."
            )


def validate_instagram_media_selection(request, workspace, accounts, formats, post_id=None):
    feed_accounts = [a for a in accounts if a.is_instagram and formats.get(str(a.pk), "feed") == "feed"]
    if not feed_accounts:
        return
    raw = request.POST.getlist("media_ids") or request.POST.getlist("pending_media_ids")
    if not raw and request.POST.get("media_submitted") != "1":
        if post_id:
            from .models import PostMedia

            assets = [
                p.media_asset
                for p in PostMedia.objects.filter(post_id=post_id, post__workspace=workspace).select_related(
                    "media_asset"
                )
            ]
        else:
            raw = request.session.get(f"pending_media_{workspace.pk}", [])
            assets = None
    else:
        assets = None
    if assets is None:
        try:
            ids = list(dict.fromkeys(str(uuid.UUID(str(value))) for value in raw if value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Lista de mídias inválida.") from exc
        by_id = {str(a.pk): a for a in MediaAsset.objects.filter(workspace=workspace, pk__in=ids)}
        assets = [by_id[key] for key in ids if key in by_id]
    if len(assets) > 1 and any(a.is_video for a in assets) and len(feed_accounts) != len(accounts):
        raise ValueError(MIXED_SELECTION_ERROR)
    strict = request.POST.get("action") in ("publish_now", "schedule", "add_to_queue", "add_to_queue_priority")
    validate_carousel_assets(assets, strict=strict)
