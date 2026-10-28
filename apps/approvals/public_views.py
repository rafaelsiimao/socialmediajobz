from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.members.decorators import require_permission

from .external import digest, ensure_valid, preview_channels, respond
from .models import ApprovalLink


def private(response):
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@never_cache
@require_http_methods(["GET", "POST"])
def public_approval(request, token):
    link = ApprovalLink.objects.select_related("post__workspace").filter(token_hash=digest(token)).first()
    if not link:
        return private(render(request, "approvals/public_closed.html", status=410))
    error = ""
    try:
        ensure_valid(link)
        if request.method == "POST":
            respond(token, request.POST.get("decision", ""), request.POST.get("comment", ""))
            return private(redirect("public_approval_thanks"))
    except ValueError:
        return private(render(request, "approvals/public_closed.html", status=410))
    except ValidationError as exc:
        error = " ".join(exc.messages)
    return private(
        render(
            request,
            "approvals/public_review.html",
            {
                "link": link,
                "channels": preview_channels(link.post),
                "error": error,
                "comment": request.POST.get("comment", ""),
            },
            status=400 if error else 200,
        )
    )


@never_cache
@require_GET
def thanks(request):
    return private(render(request, "approvals/public_thanks.html"))


@never_cache
@require_GET
def closed(request):
    return private(render(request, "approvals/public_closed.html", status=410))


@login_required
@require_permission("approve_posts")
@never_cache
@require_GET
def link_details(request, workspace_id, link_id):
    link = get_object_or_404(ApprovalLink, pk=link_id, post__workspace_id=workspace_id)
    token = request.session.get(f"approval_link_{link.pk}", "")
    url = ""
    try:
        ensure_valid(link)
    except ValueError:
        token = ""
    if token and digest(token) == link.token_hash:
        url = settings.APP_URL.rstrip("/") + reverse("public_approval", args=[token])
    return private(
        render(
            request,
            "approvals/link_details.html",
            {
                "link": link,
                "approval_url": url,
                "workspace": link.post.workspace,
                "emails": link.emails.all(),
            },
        )
    )


@login_required
@require_permission("approve_posts")
@require_POST
def retry_email(request, workspace_id, link_id):
    link = get_object_or_404(ApprovalLink, pk=link_id, post__workspace_id=workspace_id)
    from .tasks import deliver_approval_email

    for email in link.emails.filter(sent_at=None):
        deliver_approval_email(str(email.pk))
    return redirect("approvals:link_details", workspace_id=workspace_id, link_id=link.pk)
