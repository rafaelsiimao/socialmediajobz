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
