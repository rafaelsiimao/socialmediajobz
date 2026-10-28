from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.composer.metrics import platform_posts_needing_metrics, refresh_platform_post_metrics
from apps.composer.models import Post
from apps.social_accounts.models import SocialAccount
from apps.social_accounts.tasks import check_social_account_health
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import APIError
from providers.linkedin_company import LinkedInCompanyProvider
from providers.types import AccountProfile


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("No external API calls allowed")

    monkeypatch.setattr(SocialProvider, "_request", fail)


@pytest.mark.parametrize("kind,parameter", [("share", "shares"), ("ugcPost", "ugcPosts")])
def test_company_metrics_use_organization_and_correct_post_kind(kind, parameter):
    provider = LinkedInCompanyProvider({"organization_id": "123"})
    stats = {
        "impressionCount": 100,
        "uniqueImpressionsCount": 70,
        "likeCount": 5,
        "commentCount": 2,
        "shareCount": 1,
        "clickCount": 3,
        "engagement": 0.11,
    }
    response = MagicMock(json=lambda: {"elements": [{"totalShareStatistics": stats}]})
    with patch.object(provider, "_request", return_value=response) as request:
        result = provider.get_post_metrics("fake-token", f"urn:li:{kind}:456")
    params = request.call_args.kwargs["params"]
    assert params["organizationalEntity"] == "urn:li:organization:123"
    assert params[parameter] == f"List(urn:li:{kind}:456)"
    assert (result.impressions, result.reach, result.engagements) == (100, 70, 11)


def test_company_profile_reads_organization_followers():
    provider = LinkedInCompanyProvider({"organization_id": "123"})
    responses = [
        MagicMock(json=lambda: {"localizedName": "Jobz", "vanityName": "jobz"}),
        MagicMock(json=lambda: {"firstDegreeSize": 456}),
    ]
    with patch.object(provider, "_request", side_effect=responses) as request:
        profile = provider.get_profile("fake-token")
    assert profile.platform_id == "123"
    assert profile.name == "Jobz"
    assert profile.follower_count == 456
    assert "/rest/networkSizes/" in request.call_args.args[1]
    assert request.call_args.kwargs["params"]["edgeType"] == "COMPANY_FOLLOWED_BY_MEMBER"


def test_company_metrics_require_organization_instead_of_using_a_person():
    with pytest.raises(APIError):
        LinkedInCompanyProvider({}).get_post_metrics("fake-token", "urn:li:share:456")


@pytest.fixture
def company_post(organization, org_owner):
    workspace = Workspace.objects.create(organization=organization, name="Company insights")
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_company",
        account_platform_id="123",
        account_name="Jobz",
        oauth_access_token="fake-token",
        connection_status="connected",
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Test")
    return post.platform_posts.create(
        social_account=account, status="published", platform_post_id="urn:li:share:456", published_at=timezone.now()
    )


@pytest.mark.django_db
def test_refresh_selects_company_and_injects_organization(company_post):
    assert list(platform_posts_needing_metrics()) == [company_post]
    response = MagicMock(
        json=lambda: {"elements": [{"totalShareStatistics": {"impressionCount": 100, "likeCount": 5, "clickCount": 2}}]}
    )
    with patch.object(LinkedInCompanyProvider, "_request", return_value=response) as request:
        snapshot = refresh_platform_post_metrics(company_post)
    assert request.call_args.kwargs["params"]["organizationalEntity"] == "urn:li:organization:123"
    assert snapshot.views == 100
    assert snapshot.likes == 5
    assert snapshot.interactions == 7
    assert snapshot.last_error == ""


@pytest.mark.django_db
def test_health_check_uses_company_id(company_post):
    with patch("providers.get_provider") as get_provider:
        get_provider.return_value.get_profile.return_value = AccountProfile("123", "Jobz", follower_count=456)
        check_social_account_health.now(str(company_post.social_account_id))
    assert get_provider.call_args.args[1]["organization_id"] == "123"
    company_post.social_account.refresh_from_db()
    assert company_post.social_account.follower_count == 456
