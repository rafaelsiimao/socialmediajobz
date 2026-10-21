from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse

from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace


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
