"""Aggregations for the Insights page, built on PlatformPostMetrics snapshots."""

import zoneinfo
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.composer.models import PlatformPost
from apps.inbox.models import InboxMessage
from apps.social_accounts.models import SocialAccount

PERIODS = {
    "7d": "7 dias",
    "30d": "30 dias",
    "month": "Mês até hoje",
    "custom": "Personalizado",
}


@dataclass
class Period:
    key: str
    start: datetime
    end: datetime  # exclusive
    prev_start: datetime
    prev_end: datetime

    @property
    def start_date(self):
        return self.start.date()

    @property
    def end_date(self):
        return (self.end - timedelta(days=1)).date()

    @property
    def prev_start_date(self):
        return self.prev_start.date()

    @property
    def prev_end_date(self):
        return (self.prev_end - timedelta(days=1)).date()


def resolve_period(workspace, key, start_str=None, end_str=None):
    """Build the selected period and the same-length period right before it.

    Dates are whole days in the workspace timezone; ``end`` is exclusive.
    """
    tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
    today = timezone.now().astimezone(tz).date()
    if key not in PERIODS:
        key = "30d"

    if key == "7d":
        first, last = today - timedelta(days=6), today
    elif key == "month":
        first, last = today.replace(day=1), today
    elif key == "custom":
        try:
            first = date.fromisoformat(start_str or "")
            last = date.fromisoformat(end_str or "")
        except ValueError:
            key, first, last = "30d", today - timedelta(days=29), today
        if first > last:
            first, last = last, first
    else:
        first, last = today - timedelta(days=29), today

    start = datetime.combine(first, time.min, tzinfo=tz)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    length = end - start
    return Period(key=key, start=start, end=end, prev_start=start - length, prev_end=start)


def published_posts(workspace, start, end, account_id=None):
    qs = PlatformPost.objects.filter(
        post__workspace_id=workspace.id,
        status=PlatformPost.Status.PUBLISHED,
        published_at__gte=start,
        published_at__lt=end,
    )
    if account_id:
        qs = qs.filter(social_account_id=account_id)
    return qs


def _totals(posts):
    sums = posts.aggregate(
        likes=Sum("metrics__likes"),
        comments=Sum("metrics__comments"),
        views=Sum("metrics__views"),
        reach=Sum("metrics__reach"),
        interactions=Sum("metrics__interactions"),
    )
    totals = {key: value or 0 for key, value in sums.items()}
    totals["posts"] = posts.count()
    # Engagement rate = interactions / reach (Instagram), as a percentage.
    totals["engagement_rate"] = round(totals["interactions"] / totals["reach"] * 100, 1) if totals["reach"] else None
    return totals


def _delta(current, previous):
    if current is None or not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def summary(workspace, period, account_id=None):
    """Return the summary cards: value + % change vs the previous period."""
    current = _totals(published_posts(workspace, period.start, period.end, account_id))
    previous = _totals(published_posts(workspace, period.prev_start, period.prev_end, account_id))

    accounts = SocialAccount.objects.filter(
        workspace=workspace, connection_status=SocialAccount.ConnectionStatus.CONNECTED
    )
    if account_id:
        accounts = accounts.filter(id=account_id)
    followers = accounts.aggregate(total=Sum("follower_count"))["total"] or 0

    cards = [
        ("Posts", current["posts"], _delta(current["posts"], previous["posts"]), "Publicações feitas pelo sistema no período."),
        ("Seguidores", followers, None, "Total atual das contas conectadas (sem histórico de variação ainda)."),
        ("Reações", current["likes"], _delta(current["likes"], previous["likes"]), "Curtidas (Instagram) dos posts do período."),
        ("Comentários", current["comments"], _delta(current["comments"], previous["comments"]), "Comentários nos posts do período."),
        (
            "Taxa de engajamento",
            current["engagement_rate"],
            _delta(current["engagement_rate"], previous["engagement_rate"]),
            "Interações ÷ alcance dos posts do período (Instagram).",
        ),
        ("Visualizações", current["views"], _delta(current["views"], previous["views"]), "Visualizações dos posts do período (Instagram)."),
    ]
    return [
        {"label": label, "value": value, "delta": delta, "help": help_text, "is_percent": label == "Taxa de engajamento"}
        for label, value, delta, help_text in cards
    ]


def top_posts(workspace, period, order="likes", account_id=None, limit=5):
    order = order if order in ("likes", "comments") else "likes"
    return list(
        published_posts(workspace, period.start, period.end, account_id)
        .filter(metrics__fetched_at__isnull=False)
        .select_related("post", "social_account", "metrics")
        .prefetch_related("post__media_attachments__media_asset")
        .order_by(f"-metrics__{order}", "-published_at")[:limit]
    )


def takeaways(workspace, account_id=None):
    """Action cards similar to Buffer's weekly takeaways."""
    cards = []
    unanswered = InboxMessage.objects.filter(
        workspace=workspace,
        message_type=InboxMessage.MessageType.COMMENT,
        status__in=[InboxMessage.Status.UNREAD, InboxMessage.Status.OPEN],
        replies__isnull=True,
    )
    if account_id:
        unanswered = unanswered.filter(social_account_id=account_id)
    count = unanswered.count()
    if count:
        cards.append(
            {
                "title": "Sua audiência está esperando",
                "body": f"Há {count} comentário{'s' if count != 1 else ''} sem resposta. Que tal responder agora?",
                "action": "Responder comentários",
                "url_name": "inbox:feed",
            }
        )

    last_week = timezone.now() - timedelta(days=7)
    if not published_posts(workspace, last_week, timezone.now(), account_id).exists():
        cards.append(
            {
                "title": "Mantenha a constância",
                "body": "Nenhuma publicação nos últimos 7 dias. Agende um post para manter o ritmo.",
                "action": "Criar post",
                "url_name": "composer:compose",
            }
        )
    return cards
