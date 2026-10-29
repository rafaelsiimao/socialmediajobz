"""Instagram Graph API provider implementation.

Instagram's API is accessed through the Facebook Graph API. Authentication
uses the Facebook OAuth flow with Instagram-specific scopes.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from .base import SocialProvider
from .exceptions import APIError, OAuthError, ProviderError, PublishError
from .types import (
    AccountMetrics,
    AccountProfile,
    AuthType,
    CommentResult,
    InboxMessage,
    MediaType,
    OAuthTokens,
    PostMetrics,
    PostType,
    PublishContent,
    PublishResult,
    RateLimitConfig,
    ReplyResult,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v21.0"
# Each Story in a sequence is a separate publish and counts toward the
# account's 24h publishing limit.
MAX_STORY_SEQUENCE = 10
OAUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
TOKEN_URL = f"{BASE_URL}/oauth/access_token"

# Polling settings for container status checks
CONTAINER_POLL_INTERVAL = 2  # seconds
CONTAINER_POLL_MAX_ATTEMPTS = 60


def _is_video_url(url: str) -> bool:
    """Detect video by path extension, ignoring signed-URL query strings."""
    return urlsplit(url).path.lower().endswith((".mp4", ".mov"))


def _is_image_url(url: str) -> bool:
    return urlsplit(url).path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))


def _parse_ig_time(value: str) -> datetime:
    """Parse Graph API timestamps such as ``2026-10-23T16:50:51+0000``."""
    return datetime.fromisoformat(value.replace("+0000", "+00:00"))


def normalize_collaborators(value) -> list[str]:
    """Normalize up to three usernames without truncating or accepting profile URLs."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[,\s]+", value.strip())
    if not isinstance(value, (list, tuple)):
        raise ValueError("Informe nomes de usuário separados por vírgula.")
    usernames = []
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("Informe apenas nomes de usuário válidos do Instagram.")
        username = raw.strip().removeprefix("@").lower()
        if not username:
            continue
        if not re.fullmatch(r"[a-z0-9._]{1,30}", username):
            raise ValueError("Colaborador inválido. Use o nome de usuário, sem links ou espaços.")
        if username not in usernames:
            usernames.append(username)
    if len(usernames) > 3:
        raise ValueError("O Instagram permite no máximo 3 colaboradores por publicação.")
    return usernames


class InstagramProvider(SocialProvider):
    """Instagram Graph API provider (via Facebook Graph API v21.0)."""

    def __init__(self, credentials: dict | None = None):
        creds = dict(credentials or {})
        # Normalize: accept app_id/app_secret as aliases for client_id/client_secret
        if "app_id" in creds and "client_id" not in creds:
            creds["client_id"] = creds.pop("app_id")
        if "app_secret" in creds and "client_secret" not in creds:
            creds["client_secret"] = creds.pop("app_secret")
        super().__init__(creds)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def platform_name(self) -> str:
        return "Instagram"

    @property
    def auth_type(self) -> AuthType:
        return AuthType.OAUTH2

    @property
    def max_caption_length(self) -> int:
        return 2200

    @property
    def supported_post_types(self) -> list[PostType]:
        return [PostType.IMAGE, PostType.CAROUSEL, PostType.REEL, PostType.STORY]

    @property
    def supported_media_types(self) -> list[MediaType]:
        return [MediaType.JPEG, MediaType.PNG, MediaType.GIF, MediaType.MP4, MediaType.MOV]

    @property
    def required_scopes(self) -> list[str]:
        return [
            # Resolve the professional Instagram account via /me/accounts.
            "pages_show_list",
            "pages_read_engagement",
            "business_management",
            "instagram_basic",
            "instagram_content_publish",
            "instagram_manage_comments",
            "instagram_manage_insights",
            # Inbox DMs (read via the linked Page's conversations).
            "instagram_manage_messages",
            "pages_manage_metadata",
        ]

    @property
    def rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_hour=200,
            requests_per_day=5000,
            publish_per_day=100,
            extra={"published_posts_per_24h": 100},
        )

    # ------------------------------------------------------------------
    # OAuth (uses Facebook OAuth flow)
    # ------------------------------------------------------------------

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.credentials["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(self.required_scopes),
            "response_type": "code",
        }
        return f"{OAUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        resp = self._request(
            "POST",
            TOKEN_URL,
            params={
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.credentials["client_id"],
                "client_secret": self.credentials["client_secret"],
            },
        )
        data = resp.json()
        if "access_token" not in data:
            raise OAuthError(
                "Instagram token exchange failed",
                platform=self.platform_name,
                raw_response=data,
            )
        return OAuthTokens(
            access_token=data["access_token"],
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type", "Bearer"),
            raw_response=data,
        )

    def refresh_token(self, short_lived_token: str) -> OAuthTokens:
        """Exchange short-lived token for a long-lived one (same as Facebook)."""
        resp = self._request(
            "GET",
            f"{BASE_URL}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.credentials["client_id"],
                "client_secret": self.credentials["client_secret"],
                "fb_exchange_token": short_lived_token,
            },
        )
        data = resp.json()
        if "access_token" not in data:
            raise OAuthError(
                "Instagram long-lived token exchange failed",
                platform=self.platform_name,
                raw_response=data,
            )
        return OAuthTokens(
            access_token=data["access_token"],
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type", "Bearer"),
            raw_response=data,
        )

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def get_profile(self, access_token: str) -> AccountProfile:
        ig_user_id = self._get_ig_user_id(access_token)
        resp = self._request(
            "GET",
            f"{BASE_URL}/{ig_user_id}",
            access_token=access_token,
            params={"fields": "id,username,name,profile_picture_url,followers_count"},
        )
        data = resp.json()
        return AccountProfile(
            platform_id=data["id"],
            name=data.get("name", ""),
            handle=data.get("username"),
            avatar_url=data.get("profile_picture_url"),
            follower_count=data.get("followers_count", 0),
            extra=data,
        )

    # ------------------------------------------------------------------
    # Publishing (two-step container flow)
    # ------------------------------------------------------------------

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        if content.post_type == PostType.CAROUSEL and not 2 <= len(content.media_urls) <= 10:
            raise PublishError("O carrossel do Instagram aceita de 2 a 10 fotos e vídeos.", platform=self.platform_name)
        try:
            collaborators = normalize_collaborators(content.extra.get("collaborators"))
        except ValueError as exc:
            raise PublishError(str(exc), platform=self.platform_name) from exc
        if collaborators and content.post_type not in (PostType.IMAGE, PostType.CAROUSEL, PostType.REEL):
            raise PublishError(
                "Colaboração está disponível apenas para fotos, carrosséis e Reels.", platform=self.platform_name
            )
        if content.post_type == PostType.STORY and not 1 <= len(content.media_urls) <= MAX_STORY_SEQUENCE:
            raise PublishError(
                f"Story aceita de 1 a {MAX_STORY_SEQUENCE} imagens ou vídeos (um Story por mídia).",
                platform=self.platform_name,
            )
        if content.post_type == PostType.REEL and (len(content.media_urls) != 1 or _is_image_url(content.media_urls[0])):
            raise PublishError("Reel aceita exatamente 1 vídeo.", platform=self.platform_name)
        ig_user_id = content.extra.get("ig_user_id") or self._get_ig_user_id(access_token)

        if content.post_type == PostType.STORY:
            return self._publish_story_sequence(access_token, ig_user_id, content)
        if content.post_type == PostType.CAROUSEL:
            return self._publish_carousel(access_token, ig_user_id, content, collaborators=collaborators)
        return self._publish_single(access_token, ig_user_id, content, collaborators=collaborators)

    def _publish_single(
        self, access_token: str, ig_user_id: str, content: PublishContent, *, collaborators=None
    ) -> PublishResult:
        """Publish a single image or reel."""
        payload: dict = {}

        if content.text:
            payload["caption"] = content.text
        if collaborators:
            payload["collaborators"] = collaborators

        if content.post_type == PostType.REEL:
            payload["media_type"] = "REELS"
            payload["video_url"] = content.media_urls[0]
        else:
            # Default IMAGE
            payload["image_url"] = content.media_urls[0]

        # Step 1: create container
        container_id = self._create_container(access_token, ig_user_id, payload)

        # Step 2: wait for container to be ready
        self._wait_for_container(access_token, container_id)

        # Step 3: publish
        return self._publish_container(access_token, ig_user_id, container_id)

    def _publish_story_sequence(self, access_token: str, ig_user_id: str, content: PublishContent) -> PublishResult:
        """Publish each media as its own Story, in order.

        All containers are created and processed before anything is published,
        so a media failure leaves nothing live and the engine can retry safely.
        Stories have no caption field in the Graph API, so the text is ignored.
        """
        container_ids = []
        for url in content.media_urls:
            media_key = "video_url" if _is_video_url(url) else "image_url"
            container_id = self._create_container(access_token, ig_user_id, {"media_type": "STORIES", media_key: url})
            self._wait_for_container(access_token, container_id)
            container_ids.append(container_id)

        published: list[PublishResult] = []
        for container_id in container_ids:
            try:
                published.append(self._publish_container(access_token, ig_user_id, container_id))
            except ProviderError as exc:
                if not published:
                    raise
                # Some Stories are already live: report success so a retry does
                # not publish them twice, and keep the error for the team.
                logger.warning("Story sequence stopped after %d of %d: %s", len(published), len(container_ids), exc)
                return self._story_sequence_result(
                    published, error=f"{len(published)} de {len(container_ids)} Stories publicados: {exc}"
                )
        return self._story_sequence_result(published)

    @staticmethod
    def _story_sequence_result(published: list[PublishResult], error: str = "") -> PublishResult:
        extra: dict = {"story_ids": [result.platform_post_id for result in published]}
        if error:
            extra["story_errors"] = error
        return PublishResult(platform_post_id=published[0].platform_post_id, url=published[0].url, extra=extra)

    def _publish_carousel(
        self, access_token: str, ig_user_id: str, content: PublishContent, *, collaborators=None
    ) -> PublishResult:
        """Publish a carousel post with multiple media items."""
        child_ids: list[str] = []

        for url in content.media_urls:
            is_video = _is_video_url(url)
            child_payload: dict = {
                "is_carousel_item": True,
            }
            if is_video:
                child_payload["media_type"] = "VIDEO"
                child_payload["video_url"] = url
            else:
                child_payload["image_url"] = url

            child_id = self._create_container(access_token, ig_user_id, child_payload)
            self._wait_for_container(access_token, child_id)
            child_ids.append(child_id)

        # Create carousel container
        carousel_payload: dict = {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
        }
        if content.text:
            carousel_payload["caption"] = content.text
        if collaborators:
            carousel_payload["collaborators"] = collaborators

        carousel_id = self._create_container(access_token, ig_user_id, carousel_payload)
        self._wait_for_container(access_token, carousel_id)

        return self._publish_container(access_token, ig_user_id, carousel_id)

    def _create_container(self, access_token: str, ig_user_id: str, payload: dict) -> str:
        resp = self._request(
            "POST",
            f"{BASE_URL}/{ig_user_id}/media",
            access_token=access_token,
            json=payload,
        )
        data = resp.json()
        container_id = data.get("id")
        if not container_id:
            raise PublishError(
                "Failed to create Instagram media container",
                platform=self.platform_name,
                raw_response=data,
            )
        return container_id

    def _wait_for_container(self, access_token: str, container_id: str) -> None:
        """Poll container status until FINISHED or error."""
        for _ in range(CONTAINER_POLL_MAX_ATTEMPTS):
            resp = self._request(
                "GET",
                f"{BASE_URL}/{container_id}",
                access_token=access_token,
                params={"fields": "status_code,status"},
            )
            data = resp.json()
            status = data.get("status_code", "")

            if status == "FINISHED":
                return
            if status == "ERROR":
                raise PublishError(
                    f"Instagram container failed: {data.get('status', 'unknown error')}",
                    platform=self.platform_name,
                    raw_response=data,
                )

            time.sleep(CONTAINER_POLL_INTERVAL)

        raise PublishError(
            "Instagram container processing timed out",
            platform=self.platform_name,
        )

    def _publish_container(self, access_token: str, ig_user_id: str, container_id: str) -> PublishResult:
        resp = self._request(
            "POST",
            f"{BASE_URL}/{ig_user_id}/media_publish",
            access_token=access_token,
            json={"creation_id": container_id},
        )
        data = resp.json()
        media_id = data.get("id", "")
        return PublishResult(
            platform_post_id=media_id,
            url=f"https://www.instagram.com/p/{media_id}/",
            extra=data,
        )

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def publish_comment(self, access_token: str, post_id: str, text: str) -> CommentResult:
        resp = self._request(
            "POST",
            f"{BASE_URL}/{post_id}/comments",
            access_token=access_token,
            params={"fields": "id"},
            json={"message": text},
        )
        data = resp.json()
        return CommentResult(platform_comment_id=data["id"], extra=data)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # History (posts made directly in Instagram)
    # ------------------------------------------------------------------

    HISTORY_FIELDS = "id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp"

    def list_media(self, access_token: str, since: datetime | None = None, max_items: int = 500) -> list[dict]:
        """List feed posts and Reels newest first, stopping at ``since``.

        Stories are not returned by this endpoint. Follows ``paging.next``.
        """
        ig_user_id = self._get_ig_user_id(access_token)
        url: str | None = f"{BASE_URL}/{ig_user_id}/media"
        params: dict | None = {"fields": self.HISTORY_FIELDS, "limit": 50}
        items: list[dict] = []
        while url and len(items) < max_items:
            data = self._request("GET", url, access_token=access_token, params=params).json()
            params = None  # the "next" URL already carries the query
            for media in data.get("data", []):
                timestamp = _parse_ig_time(media["timestamp"])
                if since and timestamp < since:
                    return items
                items.append({**media, "timestamp": timestamp})
                if len(items) >= max_items:
                    break
            url = data.get("paging", {}).get("next")
        return items

    # Media insights metrics per product type. ``impressions``/``engagement``
    # were deprecated by Meta (media created after 2024-07-02 returns an error).
    MEDIA_INSIGHT_METRICS = {
        "STORY": ["reach", "views", "shares", "total_interactions", "replies"],
        "REELS": ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions"],
        "FEED": ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions"],
    }

    def get_post_metrics(self, access_token: str, post_id: str) -> PostMetrics:
        # Basic counters are available with instagram_basic even when insights fail.
        media = self._request(
            "GET",
            f"{BASE_URL}/{post_id}",
            access_token=access_token,
            params={"fields": "like_count,comments_count,media_product_type,permalink"},
        ).json()
        product_type = media.get("media_product_type") or "FEED"
        metrics = self.MEDIA_INSIGHT_METRICS.get(product_type, self.MEDIA_INSIGHT_METRICS["FEED"])

        values: dict = {}
        insights_error = ""
        try:
            resp = self._request(
                "GET",
                f"{BASE_URL}/{post_id}/insights",
                access_token=access_token,
                params={"metric": ",".join(metrics)},
            )
            for entry in resp.json().get("data", []):
                name = entry.get("name", "")
                val = entry.get("values", [{}])[0].get("value", 0)
                values[name] = val
        except APIError as exc:
            insights_error = str(exc)

        return PostMetrics(
            impressions=values.get("views", 0),
            reach=values.get("reach", 0),
            engagements=values.get("total_interactions", 0),
            likes=values.get("likes", media.get("like_count", 0)),
            comments=values.get("comments", media.get("comments_count", 0)),
            shares=values.get("shares", 0),
            saves=values.get("saved", 0),
            extra={
                "raw_insights": values,
                "media_product_type": product_type,
                "permalink": media.get("permalink", ""),
                "insights_error": insights_error,
            },
        )

    def get_account_metrics(self, access_token: str, date_range: tuple[datetime, datetime]) -> AccountMetrics:
        ig_user_id = self.credentials.get("ig_user_id", "me")
        metrics = ["impressions", "reach", "follower_count", "profile_views"]
        resp = self._request(
            "GET",
            f"{BASE_URL}/{ig_user_id}/insights",
            access_token=access_token,
            params={
                "metric": ",".join(metrics),
                "period": "day",
                "since": int(date_range[0].timestamp()),
                "until": int(date_range[1].timestamp()),
            },
        )
        data = resp.json()
        values: dict = {}
        for entry in data.get("data", []):
            name = entry.get("name", "")
            val = entry.get("values", [{}])[0].get("value", 0)
            values[name] = val

        return AccountMetrics(
            impressions=values.get("impressions", 0),
            reach=values.get("reach", 0),
            followers=values.get("follower_count", 0),
            profile_views=values.get("profile_views", 0),
            extra={"raw_insights": values},
        )

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------

    # Recent media scanned for new comments on each sync.
    INBOX_MEDIA_LIMIT = 25

    def get_messages(self, access_token: str, since: datetime | None = None) -> list[InboxMessage]:
        """Comments on recent media plus Instagram DMs (via the linked Page).

        DMs need ``instagram_manage_messages``; if the token lacks it, comments
        are still returned.
        """
        ig_user_id = self._get_ig_user_id(access_token)
        messages = self._get_comments(access_token, ig_user_id, since)
        try:
            messages.extend(self._get_direct_messages(access_token, ig_user_id, since))
        except APIError as exc:
            logger.warning("Instagram DMs unavailable for %s: %s", ig_user_id, exc)
        return messages

    def _get_comments(self, access_token: str, ig_user_id: str, since: datetime | None) -> list[InboxMessage]:
        resp = self._request(
            "GET",
            f"{BASE_URL}/{ig_user_id}/media",
            access_token=access_token,
            params={
                "fields": "id,caption,permalink,comments.limit(50){id,text,timestamp,username,from}",
                "limit": self.INBOX_MEDIA_LIMIT,
            },
        )
        messages: list[InboxMessage] = []
        for media in resp.json().get("data", []):
            for comment in media.get("comments", {}).get("data", []):
                sender = comment.get("from", {})
                timestamp = _parse_ig_time(comment["timestamp"])
                if sender.get("id") == ig_user_id or (since and timestamp <= since):
                    continue
                username = sender.get("username") or comment.get("username", "")
                messages.append(
                    InboxMessage(
                        platform_message_id=comment["id"],
                        sender_id=sender.get("id", ""),
                        sender_name=username,
                        text=comment.get("text", ""),
                        timestamp=timestamp,
                        message_type="comment",
                        extra={
                            "kind": "comment",
                            "sender_handle": username,
                            "media_id": media["id"],
                            "permalink": media.get("permalink", ""),
                            "media_caption": (media.get("caption") or "")[:200],
                        },
                    )
                )
        return messages

    def _get_direct_messages(self, access_token: str, ig_user_id: str, since: datetime | None) -> list[InboxMessage]:
        page_id, page_token = self._get_linked_page(access_token, ig_user_id)
        resp = self._request(
            "GET",
            f"{BASE_URL}/{page_id}/conversations",
            access_token=page_token,
            params={
                "platform": "instagram",
                "fields": "id,updated_time,messages.limit(20){id,message,from,created_time}",
            },
        )
        messages: list[InboxMessage] = []
        for convo in resp.json().get("data", []):
            for msg in convo.get("messages", {}).get("data", []):
                sender = msg.get("from", {})
                timestamp = _parse_ig_time(msg["created_time"])
                if sender.get("id") == ig_user_id or (since and timestamp <= since):
                    continue
                username = sender.get("username", "")
                messages.append(
                    InboxMessage(
                        platform_message_id=msg["id"],
                        sender_id=sender.get("id", ""),
                        sender_name=username,
                        text=msg.get("message", ""),
                        timestamp=timestamp,
                        message_type="dm",
                        extra={
                            "kind": "dm",
                            "sender_handle": username,
                            "conversation_id": convo["id"],
                            "page_id": page_id,
                            "sender_id": sender.get("id", ""),
                        },
                    )
                )
        return messages

    def _get_linked_page(self, access_token: str, ig_user_id: str) -> tuple[str, str]:
        """Return (page_id, page_access_token) for the Page linked to this IG account."""
        resp = self._request(
            "GET",
            f"{BASE_URL}/me/accounts",
            access_token=access_token,
            params={"fields": "id,access_token,instagram_business_account"},
        )
        for page in resp.json().get("data", []):
            if page.get("instagram_business_account", {}).get("id") == ig_user_id:
                return page["id"], page["access_token"]
        raise APIError("No Facebook Page linked to this Instagram account", platform=self.platform_name)

    def reply_to_message(self, access_token: str, message_id: str, text: str, extra: dict | None = None) -> ReplyResult:
        """Reply to a comment (public reply) or to a DM (via the linked Page)."""
        extra = extra or {}
        if extra.get("kind") == "dm":
            page_token = (
                self._request(
                    "GET",
                    f"{BASE_URL}/{extra['page_id']}",
                    access_token=access_token,
                    params={"fields": "access_token"},
                )
                .json()
                .get("access_token", access_token)
            )
            resp = self._request(
                "POST",
                f"{BASE_URL}/{extra['page_id']}/messages",
                access_token=page_token,
                json={"recipient": {"id": extra["sender_id"]}, "message": {"text": text}},
            )
            data = resp.json()
            return ReplyResult(platform_message_id=data.get("message_id", ""), extra=data)

        resp = self._request(
            "POST",
            f"{BASE_URL}/{message_id}/replies",
            access_token=access_token,
            json={"message": text},
        )
        data = resp.json()
        return ReplyResult(platform_message_id=data.get("id", ""), extra=data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_user_pages(self, access_token: str) -> list[dict]:
        """List the Instagram professional accounts linked to the user's Pages.

        Used by the connection flow so the user picks which Instagram account
        to connect (the token can manage several). Each entry carries the IG
        account data; no Page token, since we store the user token.
        """
        resp = self._request(
            "GET",
            f"{BASE_URL}/me/accounts",
            access_token=access_token,
            params={
                "fields": "id,name,instagram_business_account{id,username,name,profile_picture_url,followers_count}",
                "limit": 100,
            },
        )
        accounts: list[dict] = []
        for page in resp.json().get("data", []):
            ig = page.get("instagram_business_account")
            if not ig:
                continue
            accounts.append(
                {
                    "id": ig["id"],
                    "name": ig.get("name") or ig.get("username", ""),
                    "handle": ig.get("username"),
                    "category": f"Instagram @{ig.get('username', '')} · Página {page.get('name', '')}",
                    "picture": ig.get("profile_picture_url"),
                    "followers_count": ig.get("followers_count", 0),
                }
            )
        return accounts

    def _get_ig_user_id(self, access_token: str) -> str:
        """Resolve the Instagram Business Account ID from the connected
        Facebook Page.

        The IG user ID can be stored in credentials to avoid an extra API call.
        """
        if "ig_user_id" in self.credentials:
            return self.credentials["ig_user_id"]

        # Get pages and find the one with an instagram_business_account
        resp = self._request(
            "GET",
            f"{BASE_URL}/me/accounts",
            access_token=access_token,
            params={"fields": "id,instagram_business_account"},
        )
        for page in resp.json().get("data", []):
            ig_account = page.get("instagram_business_account")
            if ig_account:
                return ig_account["id"]

        raise APIError(
            "No Instagram Business Account found linked to any Facebook Page",
            platform=self.platform_name,
        )
