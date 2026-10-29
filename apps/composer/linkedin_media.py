"""Reject unsupported LinkedIn attachments before saving or scheduling."""

import uuid

from apps.media_library.models import MediaAsset
from providers.linkedin import LINKEDIN_MEDIA_ERROR


def validate_linkedin_media_selection(request, workspace, accounts, post_id=None):
    if not any(account.platform in ("linkedin_personal", "linkedin_company") for account in accounts):
        return
    raw = request.POST.getlist("media_ids") or request.POST.getlist("pending_media_ids")
    assets = None
    if not raw and request.POST.get("media_submitted") != "1":
        if post_id:
            from .models import PostMedia

            assets = [
                item.media_asset
                for item in PostMedia.objects.filter(post_id=post_id, post__workspace=workspace).select_related(
                    "media_asset"
                )
            ]
        else:
            raw = request.session.get(f"pending_media_{workspace.pk}", [])
    if assets is None:
        try:
            ids = list(dict.fromkeys(str(uuid.UUID(str(value))) for value in raw if value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Lista de mídias inválida.") from exc
        assets = list(MediaAsset.objects.filter(workspace=workspace, pk__in=ids))
    if len(assets) > 1 and any(asset.is_video for asset in assets):
        raise ValueError(LINKEDIN_MEDIA_ERROR)
