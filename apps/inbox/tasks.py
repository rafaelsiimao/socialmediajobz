"""Inbox sync engine - polls connected accounts for new messages."""

import logging
from datetime import timedelta

from background_task import background
from django.utils import timezone

from apps.members.models import WorkspaceMembership
from apps.notifications.engine import notify
from apps.notifications.models import EventType
from apps.social_accounts.models import SocialAccount
from providers import get_provider

from .models import InboxMessage, InboxSLAConfig, message_type_label, new_message_title
from .sentiment import analyze_sentiment

logger = logging.getLogger(__name__)

# How far back the first sync of a newly connected account looks.
INITIAL_SYNC_DAYS = 30


def _account_credentials(account):
    """Per-account IDs the providers need to address the right Page/IG user."""
    if account.is_instagram:
        return {"ig_user_id": account.account_platform_id}
    if account.platform == "facebook":
        return {"page_id": account.account_platform_id}
    return None


@background(schedule=0)
def run_inbox_sync_cycle():
    """Poll connected accounts for new inbox messages and check SLAs.

    Registered as a recurring task (every 5 min) in InboxConfig so that
    ``python manage.py process_tasks`` runs the inbox without a separate
    ``run_inbox_sync`` process.
    """
    engine = InboxSyncEngine()
    engine.sync_all()
    engine.check_sla()


class InboxSyncEngine:
    """Syncs inbox messages from all connected social accounts."""

    def sync_all(self):
        """Poll each connected account for new messages."""
        accounts = SocialAccount.objects.filter(
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        ).select_related("workspace")

        for account in accounts:
            try:
                self._sync_account(account)
            except Exception:
                logger.exception("Inbox sync failed for account %s", account.id)

    def _sync_account(self, account):
        """Sync messages for a single social account."""
        try:
            provider = get_provider(account.platform, _account_credentials(account))
        except ValueError:
            logger.warning("No provider for platform %s", account.platform)
            return

        last_msg = (
            InboxMessage.objects.filter(social_account=account)
            .order_by("-received_at")
            .values_list("received_at", flat=True)
            .first()
        )

        # First sync of an account: import a recent window silently instead of
        # notifying the team about every historical comment/DM.
        initial_sync = last_msg is None
        since = last_msg or timezone.now() - timedelta(days=INITIAL_SYNC_DAYS)

        try:
            messages = provider.get_messages(
                access_token=account.oauth_access_token,
                since=since,
            )
        except NotImplementedError:
            return
        except Exception:
            logger.exception(
                "get_messages() failed for account %s (%s)",
                account.id,
                account.platform,
            )
            return

        for msg in messages:
            self._upsert_message(account, msg, notify_new=not initial_sync)

    def _upsert_message(self, account, msg, notify_new=True):
        """Create or update an inbox message, deduplicating by platform_message_id."""
        obj, created = InboxMessage.objects.update_or_create(
            social_account=account,
            platform_message_id=msg.platform_message_id,
            defaults={
                "workspace": account.workspace,
                "sender_name": msg.sender_name,
                "sender_handle": msg.extra.get("sender_handle", msg.sender_id),
                "sender_avatar_url": msg.extra.get("sender_avatar_url", ""),
                "body": msg.text,
                "message_type": msg.message_type,
                "received_at": msg.timestamp,
                "extra": msg.extra,
            },
        )
        if created:
            obj.sentiment = analyze_sentiment(obj.body)
            obj.save(update_fields=["sentiment"])
            if notify_new:
                self._notify_new_message(obj)

    def _notify_new_message(self, message):
        """Send notification for a new inbox message."""
        if message.assigned_to:
            users = [message.assigned_to]
        else:
            memberships = WorkspaceMembership.objects.filter(
                workspace=message.workspace,
                workspace_role__in=["owner", "manager"],
            ).select_related("user")
            users = [m.user for m in memberships]

        for user in users:
            notify(
                user=user,
                event_type=EventType.NEW_INBOX_MESSAGE,
                title=new_message_title(message),
                body=message.body[:200],
                data={
                    "message_id": str(message.id),
                    "workspace_id": str(message.workspace_id),
                },
            )

    def check_sla(self):
        """Check for SLA-overdue messages and send notifications."""
        from datetime import timedelta

        configs = InboxSLAConfig.objects.filter(is_active=True).select_related("workspace")

        for config in configs:
            threshold = timezone.now() - timedelta(minutes=config.target_response_minutes)
            overdue_messages = InboxMessage.objects.filter(
                workspace=config.workspace,
                status__in=[InboxMessage.Status.UNREAD, InboxMessage.Status.OPEN],
                received_at__lte=threshold,
            ).exclude(extra__has_key="sla_notified")

            for message in overdue_messages:
                self._notify_sla_overdue(message, config)
                message.extra["sla_notified"] = True
                message.save(update_fields=["extra"])

    def _notify_sla_overdue(self, message, config):
        """Notify about an SLA-overdue message."""
        if message.assigned_to:
            users = [message.assigned_to]
        else:
            memberships = WorkspaceMembership.objects.filter(
                workspace=message.workspace,
                workspace_role__in=["owner", "manager"],
            ).select_related("user")
            users = [m.user for m in memberships]

        for user in users:
            notify(
                user=user,
                event_type=EventType.INBOX_SLA_OVERDUE,
                title=f"Prazo de resposta vencido: {message_type_label(message)} de {message.sender_name}",
                body=f"A meta de resposta de {config.target_response_minutes} minutos foi ultrapassada.",
                data={
                    "message_id": str(message.id),
                    "workspace_id": str(message.workspace_id),
                },
            )
