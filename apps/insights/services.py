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
    gains = [row["gained"] for row in followers_by_channel(workspace, period, account_id)["rows"] if row["gained"] is not None]
    followers_gained = sum(gains) if gains else None

    cards = [
        ("Posts", current["posts"], _delta(current["posts"], previous["posts"]), "Publicações do período (feitas pelo sistema ou importadas do Instagram)."),
        ("Seguidores", followers, None, "Total atual das contas conectadas; a variação mostra os seguidores ganhos no período."),
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
    result = [
        {"label": label, "value": value, "delta": delta, "help": help_text, "is_percent": label == "Taxa de engajamento"}
        for label, value, delta, help_text in cards
    ]
    result[1]["gained"] = followers_gained
    return result


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


# Categorical slots from the dataviz reference palette (validated, fixed order).
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
FORMATS = [("post", "Post"), ("reel", "Reel"), ("story", "Story"), ("carousel", "Carrossel")]


def channels_for(workspace, account_id=None):
    """Connected channels in a stable order; each keeps its color whatever the filter."""
    channels = list(
        SocialAccount.objects.filter(
            workspace=workspace, connection_status=SocialAccount.ConnectionStatus.CONNECTED
        ).order_by("platform", "account_name", "id")
    )
    for index, channel in enumerate(channels):
        channel.series_color = SERIES_COLORS[index % len(SERIES_COLORS)]
    if account_id:
        channels = [c for c in channels if str(c.id) == str(account_id)]
    return channels


def channel_performance(workspace, period, account_id=None):
    rows = []
    for channel in channels_for(workspace, account_id):
        current = _totals(published_posts(workspace, period.start, period.end, channel.id))
        previous = _totals(published_posts(workspace, period.prev_start, period.prev_end, channel.id))
        rows.append(
            {
                "channel": channel,
                "cells": [
                    {"value": current[key], "delta": _delta(current[key], previous[key]), "is_percent": key == "engagement_rate"}
                    for key in ("posts", "likes", "comments", "engagement_rate")
                ],
            }
        )
    return rows


def _format_of(platform_post):
    post_type = (platform_post.platform_extra or {}).get("post_type")
    return post_type if post_type in ("reel", "story", "carousel") else "post"


def posts_by_channel(workspace, period, account_id=None):
    """Posts sent per channel, split by format, with bar widths relative to the max."""
    rows = []
    for channel in channels_for(workspace, account_id):
        counts = {key: 0 for key, _ in FORMATS}
        for platform_post in published_posts(workspace, period.start, period.end, channel.id).only("platform_extra"):
            counts[_format_of(platform_post)] += 1
        rows.append({"channel": channel, "total": sum(counts.values()), "counts": counts})
    top = max((row["total"] for row in rows), default=0) or 1
    for row in rows:
        row["width"] = round(row["total"] / top * 100, 1)
        row["segments"] = [
            {
                "label": label,
                "value": row["counts"][key],
                "width": round(row["counts"][key] / top * 100, 1),
                "color": SERIES_COLORS[index],
            }
            for index, (key, label) in enumerate(FORMATS)
            if row["counts"][key]
        ]
    return {"rows": rows, "max": top, "formats": [(label, SERIES_COLORS[i]) for i, (_, label) in enumerate(FORMATS)]}


def followers_by_channel(workspace, period, account_id=None):
    """Followers at range start, gained in range and a daily series per channel.

    Uses FollowerSnapshot (recorded by the health check); today's point is the
    live ``follower_count``. Channels without history only show the current value.
    """
    from apps.social_accounts.models import FollowerSnapshot

    start_date, end_date = period.start_date, period.end_date
    today = timezone.localdate()
    rows = []
    for channel in channels_for(workspace, account_id):
        snapshots = FollowerSnapshot.objects.filter(social_account=channel)
        baseline = snapshots.filter(date__lte=start_date).order_by("-date").first()
        if baseline is None:
            baseline = snapshots.filter(date__gte=start_date, date__lte=end_date).order_by("date").first()
        series = {s.date: s.followers for s in snapshots.filter(date__gte=start_date, date__lte=end_date)}
        if start_date <= today <= end_date:
            series[today] = channel.follower_count
        current = series[max(series)] if series else channel.follower_count
        start_value = baseline.followers if baseline else None
        rows.append(
            {
                "channel": channel,
                "start": start_value,
                "current": current,
                "gained": current - start_value if start_value is not None else None,
                "series": sorted(series.items()),
            }
        )
    top = max((max(row["current"], row["start"] or 0) for row in rows), default=0) or 1
    for row in rows:
        base = row["start"] if row["start"] is not None else row["current"]
        row["start_width"] = round(min(base, row["current"]) / top * 100, 1)
        row["gain_width"] = round(max(row["gained"] or 0, 0) / top * 100, 1)
    return {"rows": rows, "max": top, "line": _line_chart(rows, start_date, end_date), "has_history": any(r["start"] is not None for r in rows)}


def _line_chart(rows, start_date, end_date, width=600, height=180, pad=8):
    """SVG polyline points per channel (shared y scale, one axis)."""
    values = [v for row in rows for _, v in row["series"]]
    if not values:
        return {}
    low, high = min(values), max(values)
    span_days = max((end_date - start_date).days, 1)
    span_values = (high - low) or 1
    lines = []
    for row in rows:
        points = []
        for day, value in row["series"]:
            x = pad + (day - start_date).days / span_days * (width - 2 * pad)
            y = height - pad - (value - low) / span_values * (height - 2 * pad)
            points.append({"x": round(x, 1), "y": round(y, 1), "date": day, "value": value})
        if points:
            lines.append({"channel": row["channel"], "points": points, "path": " ".join(f"{p['x']},{p['y']}" for p in points)})
    return {"lines": lines, "low": low, "high": high, "start": start_date, "end": end_date}
