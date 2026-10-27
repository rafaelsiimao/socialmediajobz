"""Admin-only preview of every e-mail the system sends, with sample data.

Lets the team review layout and wording without sending anything.
"""

from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.html import escape


def _sample_contexts():
    app_url = getattr(settings, "APP_URL", "http://localhost:8000").rstrip("/")
    person = SimpleNamespace(display_name="Luciana")
    now = timezone.now()
    notification = SimpleNamespace(
        title="Publicação enviada para revisão",
        body='Rafael enviou uma publicação para a sua revisão: "Trilhas de aprendizagem para líderes"',
        data={"action_url": f"{app_url}/"},
        created_at=now,
    )
    return {
        "notificacao": ("notifications/email/notification", {"notification": notification, "app_url": app_url}),
        "resumo-diario": (
            "notifications/email/digest",
            {
                "notifications": [
                    notification,
                    SimpleNamespace(title="Publicação aprovada", body="Sua publicação foi aprovada por Luciana.", created_at=now),
                ],
                "date": now,
                "app_url": app_url,
            },
        ),
        "convite-membro": (
            "members/email/invite",
            {"invited_by": person, "org_name": "Jobz", "accept_url": f"{app_url}/", "app_url": app_url},
        ),
        "portal-cliente": (
            "client_portal/email/magic_link",
            {
                "client_user": SimpleNamespace(display_name="Cliente"),
                "created_by": person,
                "workspace": SimpleNamespace(name="Grupo Jobz"),
                "magic_url": f"{app_url}/",
                "app_url": app_url,
            },
        ),
        "conectar-contas": (
            "onboarding/email/connection_link",
            {
                "org_name": "Jobz",
                "workspace_name": "Grupo Jobz",
                "link_url": f"{app_url}/",
                "expires_at": now + timedelta(days=7),
            },
        ),
        "confirmar-email": ("account/email/email_confirmation_message", {"activate_url": f"{app_url}/", "code": None}),
        "redefinir-senha": ("account/email/password_reset_key_message", {"password_reset_url": f"{app_url}/"}),
    }


def _require_staff(user):
    if not (user.is_staff or user.is_superuser):
        raise PermissionDenied("Apenas administradores.")


@login_required
def email_preview_index(request):
    _require_staff(request.user)
    links = "".join(
        f'<li><a href="{key}/">{escape(key)}</a> · <a href="{key}/?format=txt">texto</a></li>' for key in _sample_contexts()
    )
    return HttpResponse(f"<h1>Prévia dos e-mails</h1><ul>{links}</ul>")


@login_required
def email_preview(request, name):
    _require_staff(request.user)
    contexts = _sample_contexts()
    if name not in contexts:
        raise Http404
    template, context = contexts[name]
    context = {**context, "user": request.user}  # login e-mails display the user
    is_text = request.GET.get("format") == "txt"
    with translation.override("pt-br"):
        content = render_to_string(f"{template}.{'txt' if is_text else 'html'}", context)
    if is_text:
        return HttpResponse(content, content_type="text/plain; charset=utf-8")
    return HttpResponse(content)
