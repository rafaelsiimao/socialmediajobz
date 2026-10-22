from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from providers.exceptions import OAuthError
from providers.linkedin_personal import LinkedInPersonalProvider


def test_personal_oauth_only_requests_available_self_serve_permissions():
    provider = LinkedInPersonalProvider({"client_id": "fake-id"})
    url = provider.get_auth_url("https://example.com/callback/", "fake-state")
    scopes = set(parse_qs(urlsplit(url).query)["scope"][0].split())
    assert scopes == {"openid", "profile", "w_member_social"}


@pytest.mark.parametrize("full_name", ["Rafael Teste", ""])
def test_personal_profile_uses_openid_userinfo(full_name):
    provider = LinkedInPersonalProvider({})
    data = {
        "sub": "member-123",
        "name": full_name,
        "given_name": "Rafael",
        "family_name": "Teste",
        "picture": "https://example.com/avatar.png",
    }
    with patch.object(provider, "_request", return_value=MagicMock(json=lambda: data)) as request:
        profile = provider.get_profile("fake-token")
    assert request.call_args.args == ("GET", "https://api.linkedin.com/v2/userinfo")
    assert profile.platform_id == "member-123"
    assert profile.name == "Rafael Teste"
    assert profile.avatar_url == data["picture"]


def test_personal_profile_rejects_missing_member_id():
    provider = LinkedInPersonalProvider({})
    with (
        patch.object(provider, "_request", return_value=MagicMock(json=lambda: {"name": "No ID"})),
        pytest.raises(OAuthError),
    ):
        provider.get_profile("fake-token")
