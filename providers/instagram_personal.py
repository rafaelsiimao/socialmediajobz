"""Instagram API with Instagram Login provider.

Supports personal, creator, and business Instagram accounts via the
Instagram Login OAuth flow (separate from the Facebook Login path used
by the existing ``InstagramProvider``).

Docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from urllib.parse import urlencode

from .base import SocialProvider
from .exceptions import APIError, OAuthError, ProviderError, PublishError
from .instagram import (
    MAX_STORY_SEQUENCE,
    _is_image_url,
    _is_video_url,
    _parse_ig_time,
    normalize_collaborators,
)
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

AUTH_URL = "https://api.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
API_BASE = "https://graph.instagram.com/v21.0"

# Container polling
CONTAINER_POLL_INTERVAL = 2  # seconds
CONTAINER_POLL_MAX_ATTEMPTS = 60  # ~2 minutes max


class InstagramPersonalProvider(SocialProvider):
    """Instagram API provider using Instagram Login (OAuth 2.0).

    Unlike the standard ``InstagramProvider`` (which authenticates via
    Facebook Login and requires a linked Facebook Page), this provider
    uses Instagram's own OAuth flow and works with personal, creator,
    and business accounts.
    """

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
        return "Instagram (Personal)"

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
            "instagram_business_basic",
            "instagram_business_content_publish",
            "instagram_business_manage_comments",
            "instagram_business_manage_messages",
            "instagram_business_manage_insights",
        ]

    @property
    def rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_hour=200,
            requests_per_day=5000,
            publish_per_day=100,
        )

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.credentials["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(self.required_scopes),
            "response_type": "code",
            "enable_fb_login": "0",
            "force_authentication": "1",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        # Instagram Login requires form-encoded POST body
        resp = self._request(
            "POST",
            TOKEN_URL,
            data={
                "client_id": self.credentials["client_id"],
                "client_secret": self.credentials["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        body = resp.json()
        short_lived_token = body.get("access_token")
        if not short_lived_token:
            raise OAuthError(
                f"Instagram token exchange failed: {body}",
                platform=self.platform_name,
                raw_response=body,
            )

        # Exchange short-lived token (~1 hour) for long-lived token (~60 days)
        return self._exchange_for_long_lived_token(short_lived_token)

    def _exchange_for_long_lived_token(self, short_lived_token: str) -> OAuthTokens:
        resp = self._request(
            "GET",
            f"{API_BASE}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self.credentials["client_secret"],
                "access_token": short_lived_token,
            },
        )
        body = resp.json()
        if "access_token" not in body:
            raise OAuthError(
                f"Instagram long-lived token exchange failed: {body}",
                platform=self.platform_name,
                raw_response=body,
            )
        token = body["access_token"]
        return OAuthTokens(
            access_token=token,
            # Instagram Login uses the access token itself for refresh
            refresh_token=token,
            expires_in=body.get("expires_in"),
            token_type=body.get("token_type", "Bearer"),
            raw_response=body,
        )

    def refresh_token(self, refresh_token: str) -> OAuthTokens:
        """Refresh a long-lived Instagram token.

        Instagram Login uses the access token itself for refresh - there is
        no separate refresh token.
        """
        resp = self._request(
            "GET",
            f"{API_BASE}/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": refresh_token,
            },
        )
        body = resp.json()
        if "access_token" not in body:
            raise OAuthError(
                f"Instagram token refresh failed: {body}",
                platform=self.platform_name,
                raw_response=body,
            )
        token = body["access_token"]
        return OAuthTokens(
            access_token=token,
            refresh_token=token,
            expires_in=body.get("expires_in"),
            token_type=body.get("token_type", "Bearer"),
            raw_response=body,
        )

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def get_profile(self, access_token: str) -> AccountProfile:
        resp = self._request(
            "GET",
            f"{API_BASE}/me",
            access_token=access_token,
            params={
                "fields": "user_id,username,name,profile_picture_url,followers_count,biography",
            },
        )
        data = resp.json()
        return AccountProfile(
            platform_id=str(data.get("user_id", data.get("id", ""))),
            name=data.get("name", data.get("username", "")),
            handle=data.get("username"),
            avatar_url=data.get("profile_picture_url"),
            follower_count=data.get("followers_count", 0),
            extra=data,
        )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        if not content.media_urls:
            raise PublishError(
                "Instagram requires at least one media item",
                platform=self.platform_name,
            )
        try:
            collaborators = normalize_collaborators(content.extra.get("collaborators"))
        except ValueError as exc:
            raise PublishError(str(exc), platform=self.platform_name) from exc
        if collaborators and content.post_type not in (PostType.IMAGE, PostType.CAROUSEL, PostType.REEL):
            raise PublishError(
                "Colaboração está disponível apenas para fotos, carrosséis e Reels.", platform=self.platform_name
            )
        if content.post_type == PostType.STORY and len(content.media_urls) > MAX_STORY_SEQUENCE:
            raise PublishError(
                f"Story aceita de 1 a {MAX_STORY_SEQUENCE} imagens ou vídeos (um Story por mídia).",
                platform=self.platform_name,
            )
        if content.post_type == PostType.REEL and (
            len(content.media_urls) != 1 or _is_image_url(content.media_urls[0])
        ):
            raise PublishError("Reel aceita exatamente 1 vídeo.", platform=self.platform_name)

        if content.post_type == PostType.STORY:
            return self._publish_story_sequence(access_token, content)
        if content.post_type == PostType.CAROUSEL and len(content.media_urls) > 1:
            return self._publish_carousel(access_token, content, collaborators=collaborators)
        return self._publish_single(access_token, content, collaborators=collaborators)

    def _publish_single(self, access_token: str, content: PublishContent, *, collaborators=None) -> PublishResult:
        """Publish a single image or Reel."""
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

        container_id = self._create_container(access_token, payload)
        self._wait_for_container(access_token, container_id)
        return self._publish_container(access_token, container_id)

    def _publish_story_sequence(self, access_token: str, content: PublishContent) -> PublishResult:
        """Publish each media as its own Story, in order (captions are not supported).

        All containers are processed before anything is published, so a media
        failure leaves nothing live and the engine can retry safely.
        """
        container_ids = []
        for url in content.media_urls:
            media_key = "video_url" if _is_video_url(url) else "image_url"
            container_id = self._create_container(access_token, {"media_type": "STORIES", media_key: url})
            self._wait_for_container(access_token, container_id)
            container_ids.append(container_id)

        published: list[PublishResult] = []
        for container_id in container_ids:
            try:
                published.append(self._publish_container(access_token, container_id))
            except ProviderError as exc:
                if not published:
                    raise
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

    def _publish_carousel(self, access_token: str, content: PublishContent, *, collaborators=None) -> PublishResult:
        child_ids: list[str] = []

        for url in content.media_urls:
            child_payload: dict = {"is_carousel_item": True}
            if _is_video_url(url):
                child_payload["media_type"] = "VIDEO"
                child_payload["video_url"] = url
            else:
                child_payload["image_url"] = url

            child_id = self._create_container(access_token, child_payload)
            self._wait_for_container(access_token, child_id)
            child_ids.append(child_id)

        carousel_payload: dict = {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
        }
        if content.text:
            carousel_payload["caption"] = content.text
        if collaborators:
            carousel_payload["collaborators"] = collaborators

        carousel_id = self._create_container(access_token, carousel_payload)
        self._wait_for_container(access_token, carousel_id)
        return self._publish_container(access_token, carousel_id)

    def _create_container(self, access_token: str, payload: dict) -> str:
        resp = self._request(
            "POST",
            f"{API_BASE}/me/media",
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
                f"{API_BASE}/{container_id}",
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

    def _publish_container(self, access_token: str, container_id: str) -> PublishResult:
        resp = self._request(
            "POST",
            f"{API_BASE}/me/media_publish",
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
            f"{API_BASE}/{post_id}/comments",
            access_token=access_token,
            json={"message": text},
        )
        data = resp.json()
        return CommentResult(platform_comment_id=data["id"], extra=data)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    MEDIA_INSIGHT_METRICS = {
        "STORY": ["reach", "views", "shares", "total_interactions", "replies"],
        "REELS": ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions"],
        "FEED": ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions"],
    }
    HISTORY_FIELDS = "id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp"

    def get_post_metrics(self, access_token: str, post_id: str) -> PostMetrics:
        media = self._request(
            "GET",
            f"{API_BASE}/{post_id}",
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
                f"{API_BASE}/{post_id}/insights",
                access_token=access_token,
                params={"metric": ",".join(metrics)},
            )
            for entry in resp.json().get("data", []):
                values[entry.get("name", "")] = entry.get("values", [{}])[0].get("value", 0)
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

    def list_media(self, access_token: str, since: datetime | None = None, max_items: int = 500) -> list[dict]:
        """List feed posts and Reels newest first, stopping at ``since`` (no Stories)."""
        url: str | None = f"{API_BASE}/me/media"
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

    def get_account_metrics(self, access_token: str, date_range: tuple[datetime, datetime]) -> AccountMetrics:
        metrics = ["impressions", "reach", "follower_count", "profile_views"]
        resp = self._request(
            "GET",
            f"{API_BASE}/me/insights",
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

    INBOX_MEDIA_LIMIT = 25

    def get_messages(self, access_token: str, since: datetime | None = None) -> list[InboxMessage]:
        """Comments on recent media plus Instagram DMs.

        Own replies are skipped. If DMs fail (missing permission), comments are
        still returned.
        """
        own_id = self.credentials.get("ig_user_id", "")
        messages = self._get_comments(access_token, own_id, since)
        try:
            messages.extend(self._get_direct_messages(access_token, own_id, since))
        except APIError as exc:
            logger.warning("Instagram DMs unavailable: %s", exc)
        return messages

    def _get_comments(self, access_token: str, own_id: str, since: datetime | None) -> list[InboxMessage]:
        resp = self._request(
            "GET",
            f"{API_BASE}/me/media",
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
                if (own_id and sender.get("id") == own_id) or (since and timestamp <= since):
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

    def _get_direct_messages(self, access_token: str, own_id: str, since: datetime | None) -> list[InboxMessage]:
        resp = self._request(
            "GET",
            f"{API_BASE}/me/conversations",
            access_token=access_token,
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
                if (own_id and sender.get("id") == own_id) or (since and timestamp <= since):
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
                            "sender_id": sender.get("id", ""),
                        },
                    )
                )
        return messages

    def reply_to_message(self, access_token: str, message_id: str, text: str, extra: dict | None = None) -> ReplyResult:
        """Reply to a comment (public reply) or to a DM (Instagram 24h window)."""
        extra = extra or {}
        if extra.get("kind") == "dm":
            resp = self._request(
                "POST",
                f"{API_BASE}/me/messages",
                access_token=access_token,
                json={"recipient": {"id": extra["sender_id"]}, "message": {"text": text}},
            )
            data = resp.json()
            return ReplyResult(platform_message_id=data.get("message_id", ""), extra=data)

        resp = self._request(
            "POST",
            f"{API_BASE}/{message_id}/replies",
            access_token=access_token,
            json={"message": text},
        )
        data = resp.json()
        return ReplyResult(platform_message_id=data.get("id", ""), extra=data)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def revoke_token(self, access_token: str) -> bool:
        try:
            self._request(
                "DELETE",
                f"{API_BASE}/me/permissions",
                access_token=access_token,
            )
            return True
        except APIError:
            logger.warning("Failed to revoke Instagram token")
            return False
