"""Helpers for e-mail templates (absolute URLs, since e-mails have no request)."""

from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def email_app_url():
    return getattr(settings, "APP_URL", "http://localhost:8000").rstrip("/")


@register.simple_tag
def email_logo_url():
    """Absolute URL of the black Jobz logo (PNG: Gmail/Outlook block SVG)."""
    path = static("img/jobz-logo-preto.png")
    if path.startswith("http"):
        return path
    return f"{email_app_url()}/{path.lstrip('/')}"
