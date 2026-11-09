"""Background tasks for social account health checks."""

import logging
import zoneinfo
from datetime import timedelta

import httpx
from background_task import background
from django.db import transaction
from django.utils import timezone

from providers.exceptions import APIError, RateLimitError

logger = logging.getLogger(__name__)


@background(schedule=0)
def check_social_account_health(account_id: str):
    """Check health of a single social account.

    Validates the OAuth token by calling get_profile(). If the token
    is expiring soon, attempts to refresh it first.
    """
    from providers import get_provider

    from .models import FollowerSnapshot, SocialAccount

    try:
        account = SocialAccount.objects.get(id=account_id)
    except SocialAccount.DoesNotExist:
        logger.warning("Health check: account %s not found, skipping", account_id)
        return
    if account.connection_status == SocialAccount.ConnectionStatus.DISCONNECTED:
        return

    # Load app credentials from the workspace's org or env fallback
    from django.conf import settings

    from apps.credentials.models import PlatformCredential

    credentials: dict = {}
    try:
        org_id = account.workspace.organization_id
        cred = PlatformCredential.objects.for_org(org_id).get(platform=account.platform, is_configured=True)
        credentials = cred.credentials
    except PlatformCredential.DoesNotExist:
        env_creds = getattr(settings, "PLATFORM_CREDENTIALS_FROM_ENV", {})
        credentials = env_creds.get(account.platform, {})

    # For Mastodon, inject instance-specific client credentials
    if account.platform == PlatformCredential.Platform.MASTODON and account.instance_url:
        from .models import MastodonAppRegistration

        try:
            reg = MastodonAppRegistration.objects.get(instance_url=account.instance_url)
            credentials = {
                **credentials,
                "instance_url": account.instance_url,
                "client_id": reg.client_id,
                "client_secret": reg.client_secret,
            }
        except MastodonAppRegistration.DoesNotExist:
            pass

    # Instagram via Facebook Login: address this account, not the first IG found on the token.
    if account.platform == "instagram":
        credentials = {**credentials, "ig_user_id": account.account_platform_id}
    elif account.platform == "linkedin_company":
        credentials = {**credentials, "organization_id": account.account_platform_id}
    elif account.platform == "facebook":
        credentials = {**credentials, "page_id": account.account_platform_id}

    try:
        provider = get_provider(account.platform, credentials)
    except ValueError:
        logger.error("Health check: no provider for platform %s", account.platform)
        return

    # Attempt token refresh if expiring soon
    if account.is_token_expiring_soon and account.oauth_refresh_token:
        try:
            new_tokens = provider.refresh_token(account.oauth_refresh_token)
            account.oauth_access_token = new_tokens.access_token
            if new_tokens.refresh_token:
                account.oauth_refresh_token = new_tokens.refresh_token
            if new_tokens.expires_in:
                account.token_expires_at = timezone.now() + timedelta(seconds=new_tokens.expires_in)
            account.connection_status = SocialAccount.ConnectionStatus.CONNECTED
            account.last_error = ""
            logger.info("Health check: refreshed token for %s", account)
        except Exception as e:
            logger.warning("Health check: token refresh failed for %s: %s", account, e)
            account.connection_status = SocialAccount.ConnectionStatus.TOKEN_EXPIRING
            account.last_error = f"Token refresh failed: {e}"

    # Validate token by fetching profile; optional analytics may be unavailable.
    followers_observation = None
    try:
        profile = provider.get_profile(account.oauth_access_token)
        if profile.follower_count is not None:
            account.follower_count = profile.follower_count
            followers_observation = profile.follower_count
        # Meta CDN picture URLs expire after a few days: keep the stored one fresh.
        if profile.avatar_url and (not profile.platform_id or str(profile.platform_id) == account.account_platform_id):
            account.avatar_url = profile.avatar_url
        if account.connection_status != SocialAccount.ConnectionStatus.TOKEN_EXPIRING:
            account.connection_status = SocialAccount.ConnectionStatus.CONNECTED
        account.last_error = ""
        warning = profile.extra.get("follower_count_error")
        if isinstance(warning, str) and warning:
            account.last_error = f"Coleta de seguidores indisponível; conexão preservada. {warning}"
    except Exception as e:
        logger.warning("Health check: profile fetch failed for %s: %s", account, e)
        transient = isinstance(e, (RateLimitError, httpx.RequestError)) or (
            isinstance(e, APIError) and e.status_code is not None and (e.status_code == 408 or e.status_code >= 500)
        )
        preserve_connection = (
            account.platform == "linkedin_company"
            and transient
            and bool(account.oauth_access_token)
            and (account.token_expires_at is None or account.token_expires_at > timezone.now())
        )
        if not preserve_connection:
            account.connection_status = SocialAccount.ConnectionStatus.ERROR
        account.last_error = f"Health check failed: {e}"

    account.last_health_check_at = timezone.now()
    with transaction.atomic():
        current = SocialAccount.objects.select_for_update().filter(pk=account.pk).first()
        if current is None or current.updated_at != account.updated_at:
            logger.info("Health check: account %s changed during request; discarding stale result", account.pk)
            return
        if followers_observation is not None:
            FollowerSnapshot.objects.update_or_create(
                social_account=account,
                date=timezone.now().astimezone(zoneinfo.ZoneInfo(account.workspace.effective_timezone or "UTC")).date(),
                defaults={"followers": followers_observation},
            )
        account.save(
            update_fields=[
                "oauth_access_token",
                "oauth_refresh_token",
                "token_expires_at",
                "follower_count",
                "avatar_url",
                "connection_status",
                "last_error",
                "last_health_check_at",
                "updated_at",
            ]
        )


@background(schedule=0)
def schedule_all_health_checks():
    """Enqueue individual health checks for all active accounts."""
    from .models import SocialAccount

    accounts = SocialAccount.objects.filter(
        connection_status__in=[
            SocialAccount.ConnectionStatus.CONNECTED,
            SocialAccount.ConnectionStatus.TOKEN_EXPIRING,
        ]
    ).values_list("id", flat=True)

    count = 0
    for account_id in accounts:
        check_social_account_health(str(account_id))
        count += 1

    logger.info("Scheduled health checks for %d accounts", count)
