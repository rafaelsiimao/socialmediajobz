"""Threads "uninstall" and "delete data" callbacks required by the Threads app settings.

Meta POSTs a ``signed_request`` (``<signature>.<payload>``, HMAC-SHA256 with the
Threads app secret) when a user removes the app or asks for their data to be
deleted. We clear the stored tokens and mark the account disconnected; posts the
team created stay, because they are the workspace's own content.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.credentials.models import PlatformCredential

from .models import SocialAccount

logger = logging.getLogger(__name__)


def _b64decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _threads_secrets():
    env_secret = getattr(settings, "PLATFORM_CREDENTIALS_FROM_ENV", {}).get("threads", {}).get("app_secret")
    candidates = [env_secret] if env_secret else []
    for cred in PlatformCredential.objects.filter(platform="threads", is_configured=True):
        secret = (cred.credentials or {}).get("app_secret") or (cred.credentials or {}).get("client_secret")
        if secret:
            candidates.append(secret)
    return candidates


def parse_signed_request(signed_request):
    """Return the payload dict if the signature matches a known Threads secret, else None."""
    try:
        encoded_sig, encoded_payload = signed_request.split(".", 1)
        signature = _b64decode(encoded_sig)
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, AttributeError):
        return None
    for secret in _threads_secrets():
        expected = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
        if hmac.compare_digest(signature, expected):
            return payload
    return None


def _disconnect_threads_user(user_id):
    return SocialAccount.objects.filter(platform="threads", account_platform_id=str(user_id)).update(
        oauth_access_token="",
        oauth_refresh_token="",
        connection_status=SocialAccount.ConnectionStatus.DISCONNECTED,
        last_error="Acesso removido pelo usuário no Threads.",
    )


@csrf_exempt
@require_POST
def threads_uninstall(request):
    payload = parse_signed_request(request.POST.get("signed_request", ""))
    if not payload or not payload.get("user_id"):
        return HttpResponseBadRequest("invalid signed_request")
    count = _disconnect_threads_user(payload["user_id"])
    logger.info("Threads uninstall for user %s: %d account(s) disconnected", payload["user_id"], count)
    return JsonResponse({"success": True})


@csrf_exempt
@require_POST
def threads_delete(request):
    payload = parse_signed_request(request.POST.get("signed_request", ""))
    if not payload or not payload.get("user_id"):
        return HttpResponseBadRequest("invalid signed_request")
    count = _disconnect_threads_user(payload["user_id"])
    code = secrets.token_hex(8)
    logger.info("Threads data deletion %s for user %s: %d account(s) cleared", code, payload["user_id"], count)
    status_url = request.build_absolute_uri(reverse("social_accounts:threads_delete_status")) + f"?code={code}"
    return JsonResponse({"url": status_url, "confirmation_code": code})


def threads_delete_status(request):
    code = request.GET.get("code", "")
    return JsonResponse(
        {
            "confirmation_code": code,
            "status": "Os tokens de acesso do Threads foram apagados e a conta foi desconectada.",
        }
    )
