"""LinkedIn provider variant for Company Page posting.

Uses the Community Management API app with organization scopes. Posts to
Company Pages the authenticated member administers via
``w_organization_social`` and ``rw_organization_admin``.
"""

from __future__ import annotations

import logging

from .exceptions import APIError
from .linkedin import API_BASE, LINKEDIN_HEADERS, LinkedInProvider
from .types import AccountProfile, PostMetrics, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class LinkedInCompanyProvider(LinkedInProvider):
    """LinkedIn provider scoped to Company Page posting."""

    @property
    def platform_name(self) -> str:
        return "LinkedIn (Company Page)"

    @property
    def required_scopes(self) -> list[str]:
        return [
            "w_organization_social",
            "r_organization_social",
            "rw_organization_admin",
        ]

    def _organization_id(self) -> str:
        organization_id = str(self.credentials.get("organization_id") or "")
        if not organization_id.isdigit():
            raise APIError("LinkedIn Company requires the connected organization ID.", platform=self.platform_name)
        return organization_id

    def get_profile(self, access_token: str) -> AccountProfile:
        organization_id = self._organization_id()
        organization = self._request(
            "GET",
            f"{API_BASE}/rest/organizations/{organization_id}",
            access_token=access_token,
            headers=LINKEDIN_HEADERS,
        ).json()
        network = self._request(
            "GET",
            f"{API_BASE}/rest/networkSizes/urn:li:organization:{organization_id}",
            access_token=access_token,
            headers=LINKEDIN_HEADERS,
            params={"edgeType": "COMPANY_FOLLOWED_BY_MEMBER"},
        ).json()
        # Missing follower data is an API failure, not evidence of zero followers.
        if "firstDegreeSize" not in network:
            raise APIError("LinkedIn did not return the organization's follower count.", platform=self.platform_name)
        return AccountProfile(
            platform_id=organization_id,
            name=organization.get("localizedName")
            or organization.get("vanityName")
            or f"Organization {organization_id}",
            handle=organization.get("vanityName"),
            follower_count=int(network["firstDegreeSize"]),
            extra=organization,
        )

    def get_post_metrics(self, access_token: str, post_id: str) -> PostMetrics:
        organization_id = self._organization_id()
        if post_id.startswith("urn:li:share:"):
            key = "shares"
        elif post_id.startswith("urn:li:ugcPost:"):
            key = "ugcPosts"
        else:
            raise APIError("Unsupported LinkedIn post identifier.", platform=self.platform_name)
        data = self._request(
            "GET",
            f"{API_BASE}/rest/organizationalEntityShareStatistics",
            access_token=access_token,
            headers=LINKEDIN_HEADERS,
            params={
                "q": "organizationalEntity",
                "organizationalEntity": f"urn:li:organization:{organization_id}",
                key: f"List({post_id})",
            },
        ).json()
        elements = data.get("elements", [])
        stats = elements[0].get("totalShareStatistics", {}) if elements else {}
        # LinkedIn's `engagement` is a rate; the dashboard needs the interaction count.
        # Organic likeCount can be negative; snapshots store nonnegative counts.
        likes, comments, shares, clicks = (
            max(0, int(stats.get(field, 0))) for field in ("likeCount", "commentCount", "shareCount", "clickCount")
        )
        return PostMetrics(
            impressions=max(0, int(stats.get("impressionCount", 0))),
            reach=max(0, int(stats.get("uniqueImpressionsCount", 0))),
            likes=likes,
            comments=comments,
            shares=shares,
            clicks=clicks,
            engagements=likes + comments + shares + clicks,
            extra={"raw_statistics": stats, "permalink": self._post_urn_to_url(post_id)},
        )

    def get_user_pages(self, access_token: str) -> list[dict]:
        """Fetch the organization / company pages that the authenticated user administers.

        Returns a list of dicts each containing id, name, access_token, picture, and handle.
        """
        pages: list[dict] = []
        # Let API failures reach the callback: access denied is not an empty page list.
        resp = self._request(
            "GET",
            f"{API_BASE}/rest/organizationAcls",
            access_token=access_token,
            headers=LINKEDIN_HEADERS,
            params={"q": "roleAssignee", "state": "APPROVED"},
        )
        elements = resp.json().get("elements", [])

        seen_org_ids = set()
        for elem in elements:
            target = elem.get("organization") or elem.get("organizationalTarget", "")
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
                    f"{API_BASE}/rest/organizations/{org_id}",
                    access_token=access_token,
                    headers=LINKEDIN_HEADERS,
                )
                org_data = org_resp.json()
                org_name = org_data.get("localizedName") or org_data.get("vanityName") or f"Organization {org_id}"
                vanity_name = org_data.get("vanityName", "")
            except APIError:
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
