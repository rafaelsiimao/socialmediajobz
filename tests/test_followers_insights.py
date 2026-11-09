from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from apps.insights import services
from apps.social_accounts.models import FollowerSnapshot, SocialAccount
from providers.exceptions import APIError
from providers.facebook import FacebookProvider

pytest_plugins = ["tests.test_insights"]


def test_facebook_page_profile_fetches_followers():
    provider = FacebookProvider({"page_id": "123"})
    response = MagicMock(json=lambda: {"id": "123", "name": "Page", "followers_count": 560})
    with patch.object(provider, "_request", return_value=response) as request:
        profile = provider.get_profile("fake-token")
    assert request.call_args.args[1].endswith("/123")
    assert "followers_count" in request.call_args.kwargs["params"]["fields"]
    assert profile.follower_count == 560


def test_facebook_missing_followers_does_not_become_zero():
    provider = FacebookProvider({"page_id": "123"})
    with (
        patch.object(provider, "_request", return_value=MagicMock(json=lambda: {"id": "123", "name": "Page"})),
        pytest.raises(APIError),
    ):
        provider.get_profile("fake-token")


@pytest.mark.django_db
def test_uncollected_zero_is_unknown_but_collected_zero_is_real(insights_setup):
    workspace, account, _ = insights_setup
    account.follower_count = 0
    account.save()
    period = services.resolve_period(workspace, "30d")
    assert services.followers_by_channel(workspace, period)["rows"][0]["current"] is None
    assert services.summary(workspace, period)[1]["value"] is None
    FollowerSnapshot.objects.create(social_account=account, date=period.end_date, followers=0)
    row = services.followers_by_channel(workspace, period)["rows"][0]
    assert row["current"] == 0
    assert row["gained"] is None


@pytest.mark.django_db
def test_summary_does_not_present_partial_channel_total_as_complete(insights_setup):
    workspace, _, _ = insights_setup
    SocialAccount.objects.create(workspace=workspace, platform="linkedin_company", account_platform_id="unknown")
    card = services.summary(workspace, services.resolve_period(workspace, "30d"))[1]
    assert card["value"] is None
    assert card["gained"] is None


@pytest.mark.django_db
def test_historical_period_never_uses_live_followers(insights_setup):
    workspace, _, _ = insights_setup
    period = services.resolve_period(workspace, "custom", "2020-01-01", "2020-01-31")
    row = services.followers_by_channel(workspace, period)["rows"][0]
    assert row["current"] is None
    assert row["series"] == []


@pytest.mark.django_db
def test_partial_history_does_not_claim_full_period_growth(insights_setup):
    workspace, account, _ = insights_setup
    period = services.resolve_period(workspace, "30d")
    FollowerSnapshot.objects.create(social_account=account, date=period.start_date + timedelta(days=4), followers=100)
    FollowerSnapshot.objects.create(social_account=account, date=period.end_date, followers=90)
    row = services.followers_by_channel(workspace, period)["rows"][0]
    assert row["start"] is None
    assert row["current"] == 90
    assert row["gained"] is None


@pytest.mark.django_db
def test_health_addresses_facebook_page_and_preserves_count_on_failure(insights_setup):
    from apps.social_accounts.tasks import check_social_account_health

    _, account, _ = insights_setup
    account.platform = "facebook"
    account.save()
    provider = MagicMock()
    provider.get_profile.side_effect = APIError("Missing followers")
    with patch("providers.get_provider", return_value=provider) as factory:
        check_social_account_health.now(str(account.id))
    assert factory.call_args.args[1]["page_id"] == account.account_platform_id
    account.refresh_from_db()
    assert account.follower_count == 21200
    assert not account.follower_snapshots.exists()


@pytest.mark.django_db
def test_manual_refresh_queues_selected_workspace_channel(client, insights_setup):
    workspace, account, _ = insights_setup
    account.connection_status = "error"
    account.save()
    url = reverse("insights:refresh_followers", kwargs={"workspace_id": workspace.id})
    with patch("apps.social_accounts.tasks.check_social_account_health") as task:
        assert client.get(url).status_code == 405
        response = client.post(url, {"channel": str(account.id)})
    assert response.status_code == 302
    task.assert_called_once_with(str(account.id))


@pytest.mark.django_db
def test_manual_refresh_rejects_other_workspace_channel(client, insights_setup, organization):
    from apps.workspaces.models import Workspace

    workspace, _, _ = insights_setup
    other = Workspace.objects.create(organization=organization, name="Outro workspace")
    account = SocialAccount.objects.create(workspace=other, platform="facebook", account_platform_id="other")
    with patch("apps.social_accounts.tasks.check_social_account_health") as task:
        response = client.post(reverse("insights:refresh_followers", args=[workspace.pk]), {"channel": str(account.pk)})
    assert response.status_code == 404
    task.assert_not_called()


@pytest.mark.django_db
def test_manual_refresh_requires_manage_accounts(client, insights_setup):
    from apps.members.models import WorkspaceMembership

    workspace, _, author = insights_setup
    WorkspaceMembership.objects.filter(workspace=workspace, user=author).update(workspace_role="viewer")
    with patch("apps.social_accounts.tasks.check_social_account_health") as task:
        response = client.post(reverse("insights:refresh_followers", args=[workspace.pk]))
    assert response.status_code == 403
    task.assert_not_called()


@pytest.mark.django_db
def test_followers_page_explains_missing_count_and_renders_decimal_widths(client, insights_setup):
    workspace, account, _ = insights_setup
    period = services.resolve_period(workspace, "30d")
    FollowerSnapshot.objects.create(social_account=account, date=period.start_date, followers=99)
    FollowerSnapshot.objects.create(social_account=account, date=period.end_date, followers=100)
    SocialAccount.objects.create(workspace=workspace, platform="linkedin_company", account_platform_id="missing")
    body = client.get(reverse("insights:page", args=[workspace.pk])).content.decode()
    assert "Indisponível" in body
    assert "Atualizar seguidores" in body
    assert "width: 99.0%" in body
