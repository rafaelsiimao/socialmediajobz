"""Background tasks for the composer app."""

import logging

from background_task import background

logger = logging.getLogger(__name__)


@background(schedule=0)
def refresh_post_metrics():
    """Refresh analytics for recently published posts.

    Registered as a recurring task (every 3h) in ComposerConfig so that
    ``python manage.py process_tasks`` keeps the numbers up to date.
    """
    from apps.composer.metrics import refresh_recent_metrics

    count = refresh_recent_metrics()
    logger.info("Metrics refresh completed - %d post(s) checked", count)


@background(schedule=0)
def import_instagram_history_task(account_id, days=None):
    """Import posts made directly in Instagram for one account (manual button)."""
    from apps.composer.importer import IMPORT_DAYS, import_instagram_history
    from apps.social_accounts.models import SocialAccount

    account = SocialAccount.objects.filter(id=account_id, platform="instagram").first()
    if account is None:
        logger.warning("Instagram import skipped: account %s not found", account_id)
        return
    try:
        result = import_instagram_history(account, days=days or IMPORT_DAYS)
    except Exception:
        logger.exception("Instagram import failed for account %s", account_id)
        return
    logger.info("Instagram import for %s done: %s", account_id, result)


@background(schedule=0)
def sync_instagram_history():
    """Daily: bring in posts made directly in Instagram during the last days.

    Registered as a recurring task (every 24h) in ComposerConfig.
    """
    from apps.composer.importer import DAILY_SYNC_DAYS, import_instagram_history
    from apps.social_accounts.models import SocialAccount

    accounts = SocialAccount.objects.filter(
        platform="instagram", connection_status=SocialAccount.ConnectionStatus.CONNECTED
    ).select_related("workspace")
    for account in accounts:
        try:
            import_instagram_history(account, days=DAILY_SYNC_DAYS)
        except Exception:
            logger.exception("Daily Instagram sync failed for account %s", account.id)
