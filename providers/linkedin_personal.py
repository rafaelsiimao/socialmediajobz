"""LinkedIn provider variant for personal profile posting.

Uses self-service OpenID Connect and Share on LinkedIn permissions.
Posts to the authenticated member's own profile via ``w_member_social``.
"""

from __future__ import annotations

from .exceptions import OAuthError
from .linkedin import API_BASE, LinkedInProvider
from .types import AccountProfile


class LinkedInPersonalProvider(LinkedInProvider):
    """LinkedIn provider scoped to personal member posting."""

    @property
    def platform_name(self) -> str:
        return "LinkedIn (Personal)"

    @property
    def required_scopes(self) -> list[str]:
        return [
            "openid",
            "profile",
            "w_member_social",
        ]

    def get_profile(self, access_token: str) -> AccountProfile:
        response = self._request("GET", f"{API_BASE}/v2/userinfo", access_token=access_token)
        data = response.json()
        member_id = data.get("sub")
        if not member_id:
            raise OAuthError("LinkedIn did not return a member identifier.", platform=self.platform_name)
        name = data.get("name") or f"{data.get('given_name', '')} {data.get('family_name', '')}".strip()
        return AccountProfile(
            platform_id=member_id,
            name=name or "LinkedIn member",
            avatar_url=data.get("picture"),
            extra=data,
        )
