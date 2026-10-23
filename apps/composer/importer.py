"""Import posts made directly in Instagram so they show in the calendar and Insights."""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.composer.metrics import _provider_for_account, refresh_platform_post_metrics
from apps.composer.models import PlatformPost, Post

logger = logging.getLogger(__name__)

# First manual import looks back one year; the daily sync only checks recent posts.
IMPORT_DAYS = 365
DAILY_SYNC_DAYS = 7


def _post_type(media):
    if media.get("media_product_type") == "REELS":
        return "reel"
    if media.get("media_type") == "CAROUSEL_ALBUM":
        return "carousel"
    return "image"


def _media_extra(media):
    """Display data for imported posts (they have no local media attachments).

    Instagram CDN URLs expire; each import run refreshes them.
    """
    return {
        "imported": True,
        "post_type": _post_type(media),
        "media_url": media.get("media_url", ""),
        "thumbnail_url": media.get("thumbnail_url") or (media.get("media_url", "") if media.get("media_type") != "VIDEO" else ""),
        "permalink": media.get("permalink", ""),
    }


def import_instagram_history(account, days=IMPORT_DAYS):
    """Create published posts for Instagram media not yet known to the system.

    Media already linked to a PlatformPost (published by the system or
    imported before) is not duplicated; imported ones get fresh media URLs.
    Returns {"created": n, "updated": n}.
    """
    provider = _provider_for_account(account)
    provider.credentials["ig_user_id"] = account.account_platform_id
    since = timezone.now() - timedelta(days=days)
    media_items = provider.list_media(account.oauth_access_token, since=since)

    existing = {
        pp.platform_post_id: pp
        for pp in PlatformPost.objects.filter(
            social_account=account, platform_post_id__in=[m["id"] for m in media_items]
        )
    }
    created, updated = [], 0
    for media in media_items:
        known = existing.get(media["id"])
        if known:
            if (known.platform_extra or {}).get("imported"):
                known.platform_extra = {**known.platform_extra, **_media_extra(media)}
                known.save(update_fields=["platform_extra", "updated_at"])
                updated += 1
            continue
        with transaction.atomic():
            post = Post.objects.create(
                workspace=account.workspace,
                caption=media.get("caption") or "",
                scheduled_at=media["timestamp"],
                published_at=media["timestamp"],
            )
            created.append(
                PlatformPost.objects.create(
                    post=post,
                    social_account=account,
                    status=PlatformPost.Status.PUBLISHED,
                    platform_post_id=media["id"],
                    published_at=media["timestamp"],
                    platform_extra=_media_extra(media),
                )
            )

    # Metrics once at import time; the recurring metrics task keeps the recent ones fresh.
    for platform_post in created:
        refresh_platform_post_metrics(platform_post)

    logger.info("Instagram import for %s: %d created, %d updated", account.id, len(created), updated)
    return {"created": len(created), "updated": updated}
