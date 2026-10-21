from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.members.models import WorkspaceMembership
from apps.social_accounts.views import OAUTH_SESSION_KEY, _sign_state
from apps.workspaces.models import Workspace
from providers import get_provider
from providers.exceptions import APIError
from providers.linkedin import LINKEDIN_HEADERS
from providers.linkedin_company import LinkedInCompanyProvider
from providers.types import OAuthTokens, PostType, PublishContent


def test_linkedin_company_provider_instantiation():
    provider = get_provider("linkedin_company", {"client_id": "test", "client_secret": "test"})
    assert isinstance(provider, LinkedInCompanyProvider)
    assert provider.platform_name == "LinkedIn (Company Page)"
    assert "w_organization_social" in provider.required_scopes
    assert set(provider.required_scopes) == {"w_organization_social", "r_organization_social", "rw_organization_admin"}


@patch.object(LinkedInCompanyProvider, "_request")
def test_get_user_pages(mock_request):
    provider = LinkedInCompanyProvider({"client_id": "test", "client_secret": "test"})

    # 1. Mock organizationalEntityAcls response
    acls_resp = MagicMock()
    acls_resp.json.return_value = {
        "elements": [
            {
                "organizationalTarget": "urn:li:organization:123456",
                "role": "ADMINISTRATOR",
                "state": "APPROVED",
            }
        ]
    }

    # 2. Mock organization details response
    org_resp = MagicMock()
    org_resp.json.return_value = {
        "id": 123456,
        "localizedName": "Grupo Jobz",
        "vanityName": "grupo-jobz",
    }

    mock_request.side_effect = [acls_resp, org_resp]

    pages = provider.get_user_pages("mock_access_token")
    assert len(pages) == 1
    assert pages[0]["id"] == "123456"
    assert pages[0]["name"] == "Grupo Jobz"
    assert pages[0]["handle"] == "grupo-jobz"


@patch.object(LinkedInCompanyProvider, "_request")
def test_company_uses_current_rest_organization_acl(mock_request):
    mock_request.side_effect = [
        MagicMock(
            json=lambda: {
                "elements": [{"organization": "urn:li:organization:123", "role": "ADMINISTRATOR", "state": "APPROVED"}]
            }
        ),
        MagicMock(json=lambda: {"localizedName": "Jobz", "vanityName": "jobz"}),
    ]
    pages = LinkedInCompanyProvider({}).get_user_pages("fake-token")
    assert pages[0]["id"] == "123"
    assert mock_request.call_args_list[0].args[1].endswith("/rest/organizationAcls")
    assert mock_request.call_args_list[1].args[1].endswith("/rest/organizations/123")
    assert LINKEDIN_HEADERS["LinkedIn-Version"] == "202601"


@patch.object(LinkedInCompanyProvider, "_request")
def test_company_access_denied_is_not_reported_as_empty_pages(mock_request):
    mock_request.side_effect = APIError("denied", status_code=403)
    with pytest.raises(APIError):
        LinkedInCompanyProvider({}).get_user_pages("fake-token")


@pytest.mark.django_db
@pytest.mark.parametrize("access_denied", [False, True])
def test_company_callback_does_not_require_personal_profile(client, org_owner, organization, access_denied):
    workspace = Workspace.objects.create(organization=organization, name="Company OAuth")
    WorkspaceMembership.objects.create(user=org_owner, workspace=workspace, workspace_role="owner")
    client.force_login(org_owner)
    session = client.session
    session[OAUTH_SESSION_KEY] = {
        "nonce": "test-nonce",
        "workspace_id": str(workspace.id),
        "platform": "linkedin_company",
    }
    session.save()
    state = _sign_state(workspace.id, "linkedin_company", org_owner.id, "test-nonce")
    provider = MagicMock()
    provider.exchange_code.return_value = OAuthTokens(access_token="fake-token")
    provider.get_profile.side_effect = AssertionError("Company connection must not request /me")
    provider.get_user_pages.return_value = [{"id": "123", "name": "Jobz", "access_token": "fake-token"}]
    if access_denied:
        provider.get_user_pages.side_effect = APIError("private upstream error", status_code=403)
    with patch("apps.social_accounts.views._get_provider_for_platform", return_value=provider):
        response = client.get(
            reverse("social_accounts:oauth_callback", kwargs={"platform": "linkedin_company"}),
            {"code": "fake-code", "state": state},
        )
    assert response.status_code == 302
    if access_denied:
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        assert any("Community Management API" in message for message in messages)
        assert not any("private upstream error" in message for message in messages)
        assert "oauth_page_select" not in client.session
    else:
        assert response.url == reverse("social_accounts:select_account")
        assert client.session["oauth_page_select"]["pages"][0]["id"] == "123"
    provider.get_profile.assert_not_called()


@patch.object(LinkedInCompanyProvider, "_publish_text_post")
def test_publish_post_injects_organization_author(mock_publish_text):
    mock_publish_text.return_value = MagicMock(platform_post_id="urn:li:share:999", url="https://linkedin.com")
    provider = LinkedInCompanyProvider({"client_id": "test", "client_secret": "test"})

    content = PublishContent(
        text="Publicação oficial Grupo Jobz",
        post_type=PostType.TEXT,
        extra={"page_id": "123456"},
    )

    provider.publish_post("mock_token", content)

    # Verify that author was injected as urn:li:organization:123456
    assert mock_publish_text.called
    author_arg = mock_publish_text.call_args[0][1]
    assert author_arg == "urn:li:organization:123456"


@pytest.mark.django_db
def test_linkedin_company_connect_redirect_is_allowed_by_csp(client, settings, org_owner, organization):
    settings.CSP_REPORT_ONLY = False
    settings.PLATFORM_CREDENTIALS_FROM_ENV = {
        "linkedin_company": {"client_id": "test-linkedin-id", "client_secret": "test-secret"}
    }
    workspace = Workspace.objects.create(organization=organization, name="LinkedIn workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client.force_login(org_owner)
    response = client.post(
        reverse("social_accounts:connect", kwargs={"workspace_id": workspace.id}),
        {"platform": "linkedin_company"},
    )
    assert response.status_code == 302
    target = urlsplit(response["Location"])
    assert target.netloc == "www.linkedin.com"
    policy = response["Content-Security-Policy"]
    form_action = next(part.strip() for part in policy.split(";") if part.strip().startswith("form-action "))
    assert "https://www.linkedin.com" in form_action.split()
