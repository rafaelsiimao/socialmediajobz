"""LinkedIn provider variant for Company Page posting.

Uses the Community Management API app with organization scopes. Posts to
Company Pages the authenticated member administers via
``w_organization_social`` and ``rw_organization_admin``.
"""

from __future__ import annotations

import logging

from .exceptions import APIError, PublishError
from .linkedin import API_BASE, LINKEDIN_HEADERS, LinkedInProvider
from .types import AccountProfile, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class LinkedInCompanyProvider(LinkedInProvider):
    """LinkedIn provider scoped to Company Page posting."""

    @property
    def platform_name(self) -> str:
        return "LinkedIn (Company Page)"

    @property
    def required_scopes(self) -> list[str]:
        return [
            "r_basicprofile",
            "w_member_social",
            "w_organization_social",
            "r_organization_social",
            "rw_organization_admin",
        ]

    def get_user_pages(self, access_token: str) -> list[dict]:
        """Fetch the organization / company pages that the authenticated user administers.

        Returns a list of dicts each containing id, name, access_token, picture, and handle.
        """
        pages: list[dict] = []
        try:
            resp = self._request(
                "GET",
                f"{API_BASE}/v2/organizationalEntityAcls",
                access_token=access_token,
                headers=LINKEDIN_HEADERS,
                params={"q": "roleAssignee", "state": "APPROVED"},
            )
            data = resp.json()
            elements = data.get("elements", [])
        except Exception:
            logger.exception("Failed to fetch LinkedIn organizationalEntityAcls")
            elements = []

        seen_org_ids = set()
        for elem in elements:
            target = elem.get("organizationalTarget", "")
            if not target:
                continue
            # target format: urn:li:organization:12345678 or urn:li:organizationBrand:12345678
            org_id = target.split(":")[-1]
            if not org_id or org_id in seen_org_ids:
                continue
            seen_org_ids.add(org_id)

            org_name = ""
            vanity_name = ""
            logo_url = None
            try:
                org_resp = self._request(
                    "GET",
                    f"{API_BASE}/v2/organizations/{org_id}",
                    access_token=access_token,
                    headers=LINKEDIN_HEADERS,
                )
                org_data = org_resp.json()
                org_name = (
                    org_data.get("localizedName")
                    or org_data.get("vanityName")
                    or f"Organization {org_id}"
                )
                vanity_name = org_data.get("vanityName", "")
            except Exception:
                logger.warning("Could not fetch details for LinkedIn organization %s", org_id)
                org_name = f"Organization {org_id}"

            pages.append(
                {
                    "id": str(org_id),
                    "name": org_name,
                    "access_token": access_token,
                    "picture": logo_url,
                    "handle": vanity_name,
                }
            )

        return pages

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        """Publish on behalf of the organization."""
        author = content.extra.get("author")
        page_id = content.extra.get("page_id")
        if not author:
            if page_id:
                author = f"urn:li:organization:{page_id}"
            else:
                profile = self.get_profile(access_token)
                author = f"urn:li:organization:{profile.platform_id}"

        content_extra = dict(content.extra)
        content_extra["author"] = author
        content.extra = content_extra

        return super().publish_post(access_token, content)
