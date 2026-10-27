from unittest.mock import MagicMock, patch

import pytest

from apps.social_accounts.models import SocialAccount
from apps.social_accounts.tasks import check_social_account_health
from apps.workspaces.models import Workspace


@pytest.fixture
def ig_account(organization):
    workspace = Workspace.objects.create(organization=organization, name="Avatar workspace")
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-2",
        account_name="Cliente",
        connection_status="connected",
        avatar_url="https://scontent.cdninstagram.com/old.jpg?oe=EXPIRED",
    )


def _profile(platform_id, avatar):
    return MagicMock(platform_id=platform_id, avatar_url=avatar, follower_count=10)


@pytest.mark.django_db
def test_health_check_refreshes_expired_avatar_for_the_right_account(ig_account):
    provider = MagicMock()
    provider.get_profile.return_value = _profile("ig-2", "https://scontent.cdninstagram.com/new.jpg?oe=FRESH")
    with patch("providers.get_provider", return_value=provider) as get_provider:
        check_social_account_health.now(str(ig_account.id))

    assert get_provider.call_args.args[1]["ig_user_id"] == "ig-2"
    ig_account.refresh_from_db()
    assert ig_account.avatar_url.endswith("oe=FRESH")


@pytest.mark.django_db
def test_health_check_keeps_avatar_when_profile_is_another_account(ig_account):
    provider = MagicMock()
    provider.get_profile.return_value = _profile("ig-OTHER", "https://scontent.cdninstagram.com/other.jpg")
    with patch("providers.get_provider", return_value=provider):
        check_social_account_health.now(str(ig_account.id))

    ig_account.refresh_from_db()
    assert ig_account.avatar_url.endswith("oe=EXPIRED")
