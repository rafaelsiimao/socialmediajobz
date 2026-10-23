import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ComposerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.composer"
    verbose_name = "Post Composer"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._register_metrics_task, sender=self)

    @staticmethod
    def _register_metrics_task(sender, **kwargs):
        """Register the recurring post-metrics task after migrations are applied."""
        try:
            from background_task.models import Task

            from apps.composer.tasks import refresh_post_metrics

            if not Task.objects.filter(verbose_name="refresh_post_metrics").exists():
                refresh_post_metrics(
                    repeat=3 * 3600,
                    verbose_name="refresh_post_metrics",
                )
                logger.info("Registered recurring post-metrics task (every 3h)")
        except Exception:
            logger.debug("Skipping post-metrics task registration (database not ready)")
