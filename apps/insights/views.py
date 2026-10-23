"""Insights page: period summary, top posts and takeaways (Buffer-style)."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.composer.models import PlatformPostMetrics
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

from . import services


def _get_workspace(request, workspace_id):
    """Resolve workspace and enforce membership check."""
    workspace = get_object_or_404(Workspace, id=workspace_id)
    if not WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).exists():
        raise PermissionDenied("You are not a member of this workspace.")
    return workspace


def _filters(request, workspace):
    period = services.resolve_period(
        workspace, request.GET.get("period", "30d"), request.GET.get("start"), request.GET.get("end")
    )
    channels = SocialAccount.objects.filter(
        workspace=workspace, connection_status=SocialAccount.ConnectionStatus.CONNECTED
    ).order_by("platform", "account_name")
    account_id = request.GET.get("channel") or None
    if account_id and not channels.filter(id=account_id).exists():
        account_id = None
    return period, channels, account_id


def _query_without(request, key):
    params = request.GET.copy()
    params.pop(key, None)
    return params.urlencode()


@login_required
def insights_page(request, workspace_id):
    workspace = _get_workspace(request, workspace_id)
    period, channels, account_id = _filters(request, workspace)
    order = request.GET.get("order", "likes")
    if order not in ("likes", "comments"):
        order = "likes"

    return render(
        request,
        "insights/insights.html",
        {
            "workspace": workspace,
            "period": period,
            "periods": services.PERIODS,
            "channels": channels,
            "selected_channel": account_id or "",
            "order": order,
            "summary": services.summary(workspace, period, account_id),
            "top_posts": services.top_posts(workspace, period, order, account_id),
            "takeaways": services.takeaways(workspace, account_id),
            "query": request.GET.urlencode(),
            "query_without_order": _query_without(request, "order"),
        },
    )


@login_required
def export_csv(request, workspace_id):
    """Download the period's published posts with their latest metrics."""
    workspace = _get_workspace(request, workspace_id)
    period, _channels, account_id = _filters(request, workspace)
    posts = (
        services.published_posts(workspace, period.start, period.end, account_id)
        .select_related("post", "social_account", "metrics")
        .order_by("published_at")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"insights_{period.start_date:%Y-%m-%d}_{period.end_date:%Y-%m-%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM so Excel opens accents correctly
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Publicado em",
            "Rede",
            "Conta",
            "Formato",
            "Legenda",
            "Visualizações",
            "Alcance",
            "Curtidas",
            "Comentários",
            "Compartilhamentos",
            "Salvamentos",
            "Interações",
            "Link",
        ]
    )
    for pp in posts:
        try:
            metrics = pp.metrics
        except PlatformPostMetrics.DoesNotExist:
            metrics = None
        has = metrics is not None and metrics.fetched_at is not None
        writer.writerow(
            [
                pp.published_at.strftime("%d/%m/%Y %H:%M") if pp.published_at else "",
                pp.social_account.get_platform_display(),
                pp.social_account.account_name,
                (pp.platform_extra or {}).get("post_type", "post"),
                (pp.effective_caption or "")[:300],
                metrics.views if has else "",
                metrics.reach if has else "",
                metrics.likes if has else "",
                metrics.comments if has else "",
                metrics.shares if has else "",
                metrics.saves if has else "",
                metrics.interactions if has else "",
                (metrics.raw or {}).get("permalink", "") if has else "",
            ]
        )
    return response


@login_required
@require_POST
def import_history(request, workspace_id):
    """Queue the import of posts made directly in Instagram (last 12 months)."""
    from apps.composer.tasks import import_instagram_history_task

    workspace = _get_workspace(request, workspace_id)
    accounts = SocialAccount.objects.filter(
        workspace=workspace, platform="instagram", connection_status=SocialAccount.ConnectionStatus.CONNECTED
    )
    for account in accounts:
        import_instagram_history_task(str(account.id))
    if accounts:
        messages.success(
            request,
            "Importação iniciada. Os posts antigos do Instagram aparecem no calendário e aqui em alguns minutos.",
        )
    else:
        messages.error(request, "Nenhuma conta do Instagram conectada neste workspace.")
    url = reverse("insights:page", kwargs={"workspace_id": workspace.id})
    return redirect(f"{url}?{request.POST.get('query', '')}")
