from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.inbox.models import InboxMessage
from apps.inbox.tasks import InboxSyncEngine
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.base import SocialProvider
from providers.exceptions import APIError
from providers.instagram import InstagramProvider
from providers.types import InboxMessage as ProviderMessage


@pytest.fixture(autouse=True)
def forbid_external_api(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not call external provider APIs")

    monkeypatch.setattr(SocialProvider, "_request", fail)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


MEDIA_PAYLOAD = {
    "data": [
        {
            "id": "media-1",
            "caption": "Post da Jobz",
            "permalink": "https://www.instagram.com/p/abc/",
            "comments": {
                "data": [
                    {
                        "id": "c-new",
                        "text": "Adorei!",
                        "timestamp": "2026-10-23T12:00:00+0000",
                        "from": {"id": "fan-1", "username": "fan"},
                    },
                    {
                        "id": "c-own",
                        "text": "Obrigado",
                        "timestamp": "2026-10-23T12:05:00+0000",
                        "from": {"id": "ig-1", "username": "jobz"},
                    },
                    {
                        "id": "c-old",
                        "text": "Antigo",
                        "timestamp": "2026-10-01T12:00:00+0000",
                        "from": {"id": "fan-2", "username": "old"},
                    },
                ]
            },
        }
    ]
}

PAGES_PAYLOAD = {"data": [{"id": "page-1", "access_token": "page-token", "instagram_business_account": {"id": "ig-1"}}]}

CONVERSATIONS_PAYLOAD = {
    "data": [
        {
            "id": "convo-1",
            "messages": {
                "data": [
                    {
                        "id": "dm-1",
                        "message": "Oi, tenho uma dúvida",
                        "created_time": "2026-10-23T13:00:00+0000",
                        "from": {"id": "igsid-9", "username": "cliente"},
                    },
                    {
                        "id": "dm-own",
                        "message": "Olá!",
                        "created_time": "2026-10-23T13:01:00+0000",
                        "from": {"id": "ig-1", "username": "jobz"},
                    },
                ]
            },
        }
    ]
}


def test_instagram_inbox_returns_new_comments_and_dms():
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/media"):
            return _response(MEDIA_PAYLOAD)
        if url.endswith("/me/accounts"):
            return _response(PAGES_PAYLOAD)
        if url.endswith("/page-1/conversations"):
            assert kwargs["access_token"] == "page-token"
            assert kwargs["params"]["platform"] == "instagram"
            return _response(CONVERSATIONS_PAYLOAD)
        raise AssertionError(url)

    since = datetime(2026, 10, 20, tzinfo=UTC)
    with patch.object(SocialProvider, "_request", fake_request):
        messages = InstagramProvider({"ig_user_id": "ig-1"}).get_messages("user-token", since=since)

    by_id = {m.platform_message_id: m for m in messages}
    assert set(by_id) == {"c-new", "dm-1"}
    assert by_id["c-new"].message_type == "comment"
    assert by_id["c-new"].extra["permalink"] == "https://www.instagram.com/p/abc/"
    assert by_id["dm-1"].message_type == "dm"
    assert by_id["dm-1"].extra["sender_id"] == "igsid-9"


def test_instagram_comments_still_sync_when_dms_are_not_permitted():
    def fake_request(self, method, url, **kwargs):
        if url.endswith("/media"):
            return _response(MEDIA_PAYLOAD)
        raise APIError("(#10) instagram_manage_messages not granted", status_code=403)

    with patch.object(SocialProvider, "_request", fake_request):
        messages = InstagramProvider({"ig_user_id": "ig-1"}).get_messages("user-token")

    assert {m.platform_message_id for m in messages} == {"c-new", "c-old"}


def test_instagram_reply_to_comment_and_dm():
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/page-1") and method == "GET":
            return _response({"access_token": "page-token"})
        return _response({"id": "reply-1", "message_id": "mid-1"})

    provider = InstagramProvider({})
    with patch.object(SocialProvider, "_request", fake_request):
        comment_reply = provider.reply_to_message("user-token", "c-new", "Valeu!", extra={"kind": "comment"})
        dm_reply = provider.reply_to_message(
            "user-token", "dm-1", "Claro!", extra={"kind": "dm", "page_id": "page-1", "sender_id": "igsid-9"}
        )

    assert calls[0][1].endswith("/c-new/replies")
    assert comment_reply.platform_message_id == "reply-1"
    assert calls[-1][1].endswith("/page-1/messages")
    assert calls[-1][2]["access_token"] == "page-token"
    assert calls[-1][2]["json"]["recipient"] == {"id": "igsid-9"}
    assert dm_reply.platform_message_id == "mid-1"


@pytest.mark.django_db
def test_first_sync_imports_silently_then_notifies_new_messages(organization):
    workspace = Workspace.objects.create(organization=organization, name="Inbox workspace")
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-1",
        account_name="Jobz",
        connection_status="connected",
    )
    first = ProviderMessage(
        platform_message_id="c-1",
        sender_id="fan-1",
        sender_name="fan",
        text="Primeiro",
        timestamp=datetime(2026, 10, 22, tzinfo=UTC),
        extra={"kind": "comment"},
    )
    second = ProviderMessage(
        platform_message_id="c-2",
        sender_id="fan-2",
        sender_name="outro",
        text="Segundo",
        timestamp=datetime(2026, 10, 23, tzinfo=UTC),
        extra={"kind": "comment"},
    )
    provider = MagicMock()
    engine = InboxSyncEngine()

    with (
        patch("apps.inbox.tasks.get_provider", return_value=provider) as get_provider,
        patch.object(engine, "_notify_new_message") as notify,
    ):
        provider.get_messages.return_value = [first]
        engine._sync_account(account)
        assert notify.call_count == 0
        assert get_provider.call_args.args[1] == {"ig_user_id": "ig-1"}

        provider.get_messages.return_value = [first, second]
        engine._sync_account(account)
        assert notify.call_count == 1
        assert provider.get_messages.call_args.kwargs["since"] == first.timestamp

    assert InboxMessage.objects.filter(social_account=account).count() == 2


def test_instagram_requests_messaging_scopes():
    scopes = InstagramProvider({}).required_scopes
    assert "instagram_manage_messages" in scopes
    assert "pages_manage_metadata" in scopes
