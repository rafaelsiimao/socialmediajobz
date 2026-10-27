from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from apps.composer.models import Post
from apps.members.models import WorkspaceMembership
from apps.publisher.engine import PublishEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.instagram import InstagramProvider
from providers.types import PublishResult


@pytest.fixture(autouse=True)
def forbid_external_api(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not call external provider APIs")

    monkeypatch.setattr(SocialProvider, "_request", fail)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_get_user_pages_lists_every_linked_instagram_account():
    payload = {
        "data": [
            {"id": "p1", "name": "Jobz", "instagram_business_account": {"id": "ig-jobz", "username": "jobz"}},
            {"id": "p2", "name": "Sem Instagram"},
            {
                "id": "p3",
                "name": "Cliente",
                "instagram_business_account": {
                    "id": "ig-cliente",
                    "username": "cliente",
                    "profile_picture_url": "https://cdn/x.jpg",
                    "followers_count": 900,
                },
            },
        ]
    }
    with patch.object(SocialProvider, "_request", lambda *a, **k: _response(payload)):
        accounts = InstagramProvider({}).get_user_pages("user-token")

    assert [a["id"] for a in accounts] == ["ig-jobz", "ig-cliente"]
    assert accounts[1]["handle"] == "cliente" and accounts[1]["followers_count"] == 900
    assert "access_token" not in accounts[1]  # the user token is stored, not a Page token


@pytest.fixture
def workspace(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Clientes")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client.force_login(org_owner)
    return workspace


@pytest.mark.django_db
def test_select_instagram_account_stores_user_token_with_expiry(client, workspace):
    session = client.session
    session["oauth_page_select"] = {
        "workspace_id": str(workspace.id),
        "platform": "instagram",
        "user_tokens": {"access_token": "user-token", "refresh_token": None, "expires_in": 5184000},
        "pages": [
            {"id": "ig-jobz", "name": "Jobz", "handle": "jobz"},
            {"id": "ig-cliente", "name": "Cliente", "handle": "cliente"},
        ],
    }
    session.save()

    response = client.post(reverse("social_accounts:select_account"), {"selected_pages": ["ig-cliente"]})

    assert response.status_code == 302
    account = SocialAccount.objects.get(workspace=workspace, platform="instagram")
    assert account.account_platform_id == "ig-cliente"
    assert account.oauth_access_token == "user-token"
    assert account.token_expires_at is not None
    assert not SocialAccount.objects.filter(account_platform_id="ig-jobz").exists()


@pytest.mark.django_db
def test_publish_targets_the_post_account_not_the_first_instagram(workspace, org_owner):
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-cliente",
        account_name="Cliente",
        connection_status="connected",
        oauth_access_token="user-token",
    )
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Post do cliente")
    platform_post = post.platform_posts.create(social_account=account, status="publishing")

    captured = {}

    def fake_publish(self, access_token, content):
        captured["ig_user_id"] = content.extra.get("ig_user_id")
        return PublishResult("media-1")

    with patch.object(InstagramProvider, "publish_post", fake_publish):
        result = PublishEngine()._dispatch_to_provider(platform_post)

    assert result["success"] is True
    assert captured["ig_user_id"] == "ig-cliente"
