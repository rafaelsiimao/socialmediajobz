from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse

from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.instagram import InstagramProvider


def test_instagram_requests_page_discovery_permissions():
    provider = InstagramProvider({"app_id": "test-app", "app_secret": "test-secret"})
    query = parse_qs(urlsplit(provider.get_auth_url("https://example.com/callback/", "test-state")).query)
    scopes = set(query["scope"][0].split(","))
    assert {"pages_show_list", "pages_read_engagement", "business_management", "instagram_basic"} <= scopes


@pytest.mark.django_db
@pytest.mark.parametrize("platform", ["facebook", "instagram"])
def test_meta_connect_redirect_is_allowed_by_csp(client, settings, org_owner, organization, platform):
    settings.CSP_REPORT_ONLY = False
    settings.PLATFORM_CREDENTIALS_FROM_ENV = {
        platform: {"app_id": "test-app", "app_secret": "test-secret"}
    }
    workspace = Workspace.objects.create(organization=organization, name="OAuth workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client.force_login(org_owner)
    response = client.post(
        reverse("social_accounts:connect", kwargs={"workspace_id": workspace.id}),
        {"platform": platform},
    )
    assert response.status_code == 302
    target = urlsplit(response["Location"])
    assert target.netloc == "www.facebook.com"
    assert parse_qs(target.query)["client_id"] == ["test-app"]
    policy = response["Content-Security-Policy"]
    form_action = next(part.strip() for part in policy.split(";") if part.strip().startswith("form-action "))
    assert "https://www.facebook.com" in form_action.split()


@pytest.mark.django_db
def test_select_facebook_page_preserves_long_avatar_url(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Facebook workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    avatar_url = "https://example.com/picture.jpg?signature=" + "a" * 1200
    # SQLite does not enforce varchar lengths, so also exercise model validation.
    SocialAccount._meta.get_field("avatar_url").clean(avatar_url, None)
    client.force_login(org_owner)
    session = client.session
    session["oauth_page_select"] = {
        "workspace_id": str(workspace.id),
        "platform": "facebook",
        "user_tokens": {"access_token": "test-user-token", "refresh_token": None},
        "pages": [{"id": "123", "name": "Test Page", "picture": avatar_url, "access_token": "test-page-token"}],
    }
    session.save()
    response = client.post(reverse("social_accounts:select_account"), {"selected_pages": ["123"]})
    assert response.status_code == 302
    account = SocialAccount.objects.get(workspace=workspace, platform="facebook", account_platform_id="123")
    assert account.avatar_url == avatar_url
    assert account.oauth_access_token == "test-page-token"
