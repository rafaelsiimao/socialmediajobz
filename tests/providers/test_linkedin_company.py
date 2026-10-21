from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse

from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace
from providers import get_provider
from providers.linkedin_company import LinkedInCompanyProvider
from providers.types import PublishContent, PostType


def test_linkedin_company_provider_instantiation():
    provider = get_provider("linkedin_company", {"client_id": "test", "client_secret": "test"})
    assert isinstance(provider, LinkedInCompanyProvider)
    assert provider.platform_name == "LinkedIn (Company Page)"
    assert "w_organization_social" in provider.required_scopes


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
