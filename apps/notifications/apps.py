import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "Notifications"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._register_notification_tasks, sender=self)

    @staticmethod
    def _register_notification_tasks(sender, **kwargs):
        """Use the existing background worker to retry failed deliveries."""
        try:
            from background_task.models import Task

            from .tasks import retry_notification_deliveries

            if not Task.objects.filter(verbose_name="retry_notification_deliveries").exists():
                retry_notification_deliveries(repeat=60, verbose_name="retry_notification_deliveries")
        except Exception:
            logger.debug("Skipping notification task registration (database not ready)")
