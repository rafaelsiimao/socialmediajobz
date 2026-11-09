from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.urls import reverse
from django.utils import timezone

from apps.composer.models import Post
from apps.social_accounts.models import FollowerSnapshot, SocialAccount
from apps.social_accounts.tasks import check_social_account_health
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import APIError, RateLimitError
from providers.linkedin_company import LinkedInCompanyProvider
from providers.types import AccountProfile


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("No external API calls allowed")

    monkeypatch.setattr(SocialProvider, "_request", fail)


@pytest.fixture
def company_post(organization, org_owner):
    workspace = Workspace.objects.create(organization=organization, name="Company health")
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_company",
        account_platform_id="123",
        account_name="Jobz",
        oauth_access_token="fake-token",
        connection_status="connected",
    )
    post = Post.objects.create(workspace=workspace, author=org_owner)
    return post.platform_posts.create(social_account=account)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "failure",
    [
        APIError("Forbidden", status_code=403),
        RateLimitError("Limit"),
        APIError("Unavailable", status_code=500),
        httpx.ReadTimeout("Timeout"),
    ],
)
def test_follower_failure_does_not_disconnect_company_or_write_zero(company_post, failure):
    account = company_post.social_account
    account.follower_count = 456
    account.save()
    with patch.object(
        LinkedInCompanyProvider, "_request", side_effect=[MagicMock(json=lambda: {"localizedName": "Jobz"}), failure]
    ):
        check_social_account_health.now(str(account.pk))
    account.refresh_from_db()
    assert account.connection_status == "connected"
    assert account.follower_count == 456
    assert account.last_error
    assert not FollowerSnapshot.objects.filter(social_account=account).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("network", [{}, {"firstDegreeSize": -1}, {"firstDegreeSize": None}])
def test_missing_follower_field_is_not_token_failure(company_post, network):
    account = company_post.social_account
    with patch.object(
        LinkedInCompanyProvider,
        "_request",
        side_effect=[MagicMock(json=lambda: {"localizedName": "Jobz"}), MagicMock(json=lambda: network)],
    ):
        check_social_account_health.now(str(account.pk))
    account.refresh_from_db()
    assert account.connection_status == "connected"
    assert not account.follower_snapshots.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("at_network", [False, True])
def test_real_unauthorized_still_requires_reconnect(company_post, at_network):
    responses = [APIError("Invalid access token", status_code=401)]
    if at_network:
        responses.insert(0, MagicMock(json=lambda: {"localizedName": "Jobz"}))
    with patch.object(LinkedInCompanyProvider, "_request", side_effect=responses):
        check_social_account_health.now(str(company_post.social_account_id))
    company_post.social_account.refresh_from_db()
    assert company_post.social_account.needs_reconnect


@pytest.mark.django_db
def test_organization_forbidden_still_requires_attention(company_post):
    with patch.object(LinkedInCompanyProvider, "_request", side_effect=APIError("Lost access", status_code=403)):
        check_social_account_health.now(str(company_post.social_account_id))
    company_post.social_account.refresh_from_db()
    assert company_post.social_account.connection_status == "error"


@pytest.mark.django_db
@pytest.mark.parametrize("expired", [False, True])
def test_temporary_organization_failure_does_not_disconnect_valid_token(company_post, expired):
    account = company_post.social_account
    account.token_expires_at = timezone.now() + timedelta(days=-1 if expired else 30)
    account.save()
    with patch.object(LinkedInCompanyProvider, "_request", side_effect=APIError("Unavailable", status_code=503)):
        check_social_account_health.now(str(account.pk))
    account.refresh_from_db()
    assert account.connection_status == ("error" if expired else "connected")
    assert account.last_error


@pytest.mark.django_db
def test_health_started_before_reconnect_cannot_overwrite_new_token(company_post):
    account = company_post.social_account

    def reconnected_during_check(*args):
        account.oauth_access_token = "new-test-token"
        account.connection_status = "connected"
        account.last_error = ""
        account.save()
        raise APIError("Old token revoked", status_code=401)

    with patch.object(LinkedInCompanyProvider, "get_profile", side_effect=reconnected_during_check):
        check_social_account_health.now(str(account.pk))
    account.refresh_from_db()
    assert account.oauth_access_token == "new-test-token"
    assert account.connection_status == "connected"
    assert account.last_error == ""


@pytest.mark.django_db
def test_connected_collection_warning_is_visible(client, company_post, org_owner):
    from apps.members.models import WorkspaceMembership

    account = company_post.social_account
    WorkspaceMembership.objects.create(user=org_owner, workspace=account.workspace, workspace_role="owner")
    account.last_error = "Coleta de seguidores indisponível; conexão preservada."
    account.save()
    client.force_login(org_owner)
    from apps.workspaces.models import Workspace

    other = Workspace.objects.create(organization=account.workspace.organization, name="Outro")
    WorkspaceMembership.objects.create(user=org_owner, workspace=other, workspace_role="owner")
    for workspace_id in [account.workspace_id, other.pk, account.workspace_id]:
        response = client.get(reverse("social_accounts:list", args=[workspace_id]))
        assert response.status_code == 200
        if workspace_id == account.workspace_id:
            assert "Coleta de seguidores indisponível" in response.content.decode()
            assert account.pk in [channel.pk for channel in response.context["sidebar_channels"]]
            assert account.pk not in [channel.pk for channel in response.context["sidebar_unhealthy_channels"]]
    account.refresh_from_db()
    assert account.connection_status == "connected"


@pytest.mark.django_db
def test_profile_without_followers_preserves_existing_count_on_oauth_update(company_post):
    from apps.social_accounts.views import _create_or_update_account

    account = company_post.social_account
    account.follower_count = 456
    account.save()
    _create_or_update_account(
        workspace_id=account.workspace_id,
        platform="linkedin_company",
        profile=AccountProfile("123", "Jobz", follower_count=None),
        access_token="new-test-token",
    )
    account.refresh_from_db()
    assert account.follower_count == 456


@pytest.mark.django_db
@pytest.mark.parametrize("followers", [0, 123])
def test_successful_company_check_clears_warning_and_recovers(company_post, followers):
    account = company_post.social_account
    account.connection_status = "error"
    account.last_error = "Previous failure"
    account.save()
    with patch.object(
        LinkedInCompanyProvider,
        "_request",
        side_effect=[
            MagicMock(json=lambda: {"localizedName": "Jobz"}),
            MagicMock(json=lambda: {"firstDegreeSize": followers}),
        ],
    ):
        check_social_account_health.now(str(account.pk))
    account.refresh_from_db()
    assert account.connection_status == "connected"
    assert account.last_error == ""
    assert account.follower_snapshots.get().followers == followers


@pytest.mark.django_db
def test_successful_old_check_does_not_write_snapshot_after_reconnect(company_post):
    account = company_post.social_account

    def reconnected(*args):
        account.oauth_access_token = "new-test-token"
        account.save()
        return AccountProfile("123", "Jobz", follower_count=111)

    with patch.object(LinkedInCompanyProvider, "get_profile", side_effect=reconnected):
        check_social_account_health.now(str(account.pk))
    assert not account.follower_snapshots.exists()
    account.refresh_from_db()
    assert account.oauth_access_token == "new-test-token"


@pytest.mark.django_db
def test_disconnected_company_is_not_resurrected_by_queued_check(company_post):
    account = company_post.social_account
    account.connection_status = "disconnected"
    account.save()
    with patch.object(LinkedInCompanyProvider, "get_profile") as profile:
        check_social_account_health.now(str(account.pk))
    profile.assert_not_called()
    account.refresh_from_db()
    assert account.connection_status == "disconnected"
