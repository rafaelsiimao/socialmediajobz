"""Fetch performance metrics for published PlatformPosts from the platforms."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.composer.models import PlatformPost, PlatformPostMetrics
from apps.credentials.models import PlatformCredential
from providers import get_provider

logger = logging.getLogger(__name__)

# Platforms whose provider implements get_post_metrics with current Meta metrics.
# Facebook is disabled until the "nonexisting field (shares)" error is fixed
# (see PROXIMA_SESSAO.md).
METRICS_PLATFORMS = ("instagram", "instagram_personal", "threads")
# Only keep refreshing recent posts; older numbers barely change.
METRICS_MAX_AGE_DAYS = 90
METRICS_BATCH_SIZE = 200


def _provider_for_account(account):
    try:
        cred = PlatformCredential.objects.for_org(account.workspace.organization_id).get(
            platform=account.platform, is_configured=True
        )
        credentials = dict(cred.credentials)
    except PlatformCredential.DoesNotExist:
        env_creds = getattr(settings, "PLATFORM_CREDENTIALS_FROM_ENV", {})
        credentials = dict(env_creds.get(account.platform, {}))
    return get_provider(account.platform, credentials)


def refresh_platform_post_metrics(platform_post):
    """Fetch and store the latest metrics for one published PlatformPost.

    Errors are recorded on the snapshot instead of raised, so one bad post
    does not stop the batch.
    """
    snapshot, _ = PlatformPostMetrics.objects.get_or_create(platform_post=platform_post)
    account = platform_post.social_account
    try:
        provider = _provider_for_account(account)
        result = provider.get_post_metrics(account.oauth_access_token, platform_post.platform_post_id)
    except Exception as exc:
        logger.warning("Metrics fetch failed for PlatformPost %s: %s", platform_post.id, exc)
        snapshot.last_error = str(exc)[:1000]
        snapshot.save(update_fields=["last_error", "updated_at"])
        return snapshot

    snapshot.views = result.impressions or result.video_views
    snapshot.reach = result.reach
    snapshot.likes = result.likes
    snapshot.comments = result.comments
    snapshot.shares = result.shares
    snapshot.saves = result.saves
    snapshot.interactions = result.engagements
    snapshot.raw = result.extra
    snapshot.fetched_at = timezone.now()
    snapshot.last_error = result.extra.get("insights_error", "")
    snapshot.save()
    return snapshot


def platform_posts_needing_metrics():
    since = timezone.now() - timedelta(days=METRICS_MAX_AGE_DAYS)
    return (
        PlatformPost.objects.filter(
            status=PlatformPost.Status.PUBLISHED,
            social_account__platform__in=METRICS_PLATFORMS,
            published_at__gte=since,
        )
        .exclude(platform_post_id="")
        .select_related("social_account__workspace")
        .order_by("-published_at")[:METRICS_BATCH_SIZE]
    )


def refresh_recent_metrics():
    """Refresh metrics for recently published posts. Returns how many were fetched."""
    count = 0
    for platform_post in platform_posts_needing_metrics():
        refresh_platform_post_metrics(platform_post)
        count += 1
    return count
