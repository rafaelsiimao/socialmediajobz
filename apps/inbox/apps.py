import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class InboxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inbox"
    verbose_name = "Inbox"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._register_inbox_sync_task, sender=self)

    @staticmethod
    def _register_inbox_sync_task(sender, **kwargs):
        """Register the recurring inbox sync task after migrations are applied."""
        try:
            from background_task.models import Task

            from apps.inbox.tasks import run_inbox_sync_cycle

            if not Task.objects.filter(verbose_name="run_inbox_sync_cycle").exists():
                run_inbox_sync_cycle(
                    repeat=5 * 60,
                    verbose_name="run_inbox_sync_cycle",
                )
                logger.info("Registered recurring inbox sync task (every 5 min)")
        except Exception:
            logger.debug("Skipping inbox sync task registration (database not ready)")
