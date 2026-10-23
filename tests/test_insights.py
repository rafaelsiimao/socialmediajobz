from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.composer.models import PlatformPostMetrics, Post
from apps.inbox.models import InboxMessage
from apps.insights import services
from apps.insights.templatetags.insights_tags import br_delta, br_number
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def insights_setup(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Insights workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-i",
        account_name="Jobz IG",
        connection_status="connected",
        follower_count=21200,
    )
    client.force_login(org_owner)
    return workspace, account, org_owner


def _published(workspace, account, author, days_ago, caption, **metrics):
    when = timezone.now() - timedelta(days=days_ago)
    post = Post.objects.create(workspace=workspace, author=author, caption=caption, scheduled_at=when)
    pp = post.platform_posts.create(
        social_account=account, status="published", platform_post_id=f"m-{caption}", published_at=when
    )
    if metrics:
        PlatformPostMetrics.objects.create(platform_post=pp, fetched_at=timezone.now(), **metrics)
    return pp


@pytest.mark.django_db
def test_resolve_period_variants(insights_setup):
    workspace, _, _ = insights_setup
    week = services.resolve_period(workspace, "7d")
    assert (week.end - week.start).days == 7
    assert week.prev_end == week.start

    custom = services.resolve_period(workspace, "custom", "2026-10-10", "2026-10-01")
    assert (custom.start_date, custom.end_date) == (date(2026, 10, 1), date(2026, 10, 10))

    fallback = services.resolve_period(workspace, "custom", "x", "y")
    assert fallback.key == "30d"


@pytest.mark.django_db
def test_summary_compares_with_previous_period(insights_setup):
    workspace, account, author = insights_setup
    _published(workspace, account, author, 2, "atual", likes=30, comments=4, views=500, reach=200, interactions=40)
    _published(workspace, account, author, 9, "anterior", likes=20, comments=8, views=1000, reach=100, interactions=10)

    cards = {c["label"]: c for c in services.summary(workspace, services.resolve_period(workspace, "7d"))}
    assert cards["Posts"]["value"] == 1 and cards["Posts"]["delta"] == 0
    assert cards["Reações"]["value"] == 30 and cards["Reações"]["delta"] == 50.0
    assert cards["Comentários"]["delta"] == -50.0
    assert cards["Taxa de engajamento"]["value"] == 20.0
    assert cards["Seguidores"]["value"] == 21200


@pytest.mark.django_db
def test_page_renders_summary_top_posts_and_takeaways(client, insights_setup):
    workspace, account, author = insights_setup
    top = _published(workspace, account, author, 1, "campeao", likes=46, comments=1, reach=300, interactions=50)
    _published(workspace, account, author, 3, "segundo", likes=18, comments=9, reach=100, interactions=30)
    _published(workspace, account, author, 4, "sem-metricas")
    InboxMessage.objects.create(
        workspace=workspace,
        social_account=account,
        platform_message_id="c-1",
        sender_name="fan",
        body="Oi",
        message_type="comment",
        received_at=timezone.now(),
    )
    url = reverse("insights:page", kwargs={"workspace_id": workspace.id})

    body = client.get(url).content.decode()
    assert "Resumo" in body and "Top 5 posts" in body
    assert "21.200" in body
    assert "1 comentário sem resposta" in body
    detail_url = reverse(
        "calendar:published_post_detail", kwargs={"workspace_id": workspace.id, "platform_post_id": top.id}
    )
    assert detail_url in body
    assert body.index("campeao") < body.index("segundo")
    assert "sem-metricas" not in body

    by_comments = client.get(url, {"order": "comments"}).content.decode()
    assert by_comments.index("segundo") < by_comments.index("campeao")


@pytest.mark.django_db
def test_export_csv_lists_period_posts(client, insights_setup):
    workspace, account, author = insights_setup
    _published(workspace, account, author, 1, "exportado", likes=7, comments=2)
    response = client.get(reverse("insights:export_csv", kwargs={"workspace_id": workspace.id}), {"period": "7d"})
    content = response.content.decode("utf-8-sig")
    assert response["Content-Type"].startswith("text/csv")
    assert "Curtidas" in content.splitlines()[0]
    assert "exportado" in content and ";7;2;" in content


@pytest.mark.django_db
def test_insights_requires_membership(client, insights_setup, django_user_model):
    workspace, _, _ = insights_setup
    outsider = django_user_model.objects.create_user(
        email="outsider@example.com", password="x-test-123", tos_accepted_at=timezone.now()
    )
    client.force_login(outsider)
    assert client.get(reverse("insights:page", kwargs={"workspace_id": workspace.id})).status_code == 403


def test_brazilian_number_format():
    assert br_number(21200) == "21.200"
    assert br_number(3.5) == "3,5"
    assert br_number(None) == "-"
    assert br_delta(-37.1) == "-37,1%"
    assert br_delta(72.7) == "+72,7%"


@pytest.mark.django_db
def test_channel_performance_and_posts_by_format(insights_setup):
    workspace, account, author = insights_setup
    reel = _published(workspace, account, author, 1, "reel", likes=10, comments=2, reach=50, interactions=12)
    reel.platform_extra = {"post_type": "reel"}
    reel.save(update_fields=["platform_extra"])
    _published(workspace, account, author, 2, "feed", likes=5, comments=1, reach=50, interactions=6)
    period = services.resolve_period(workspace, "7d")

    rows = services.channel_performance(workspace, period)
    assert rows[0]["channel"] == account
    assert [cell["value"] for cell in rows[0]["cells"]] == [2, 15, 3, 18.0]

    chart = services.posts_by_channel(workspace, period)
    row = chart["rows"][0]
    assert row["total"] == 2 and row["width"] == 100.0
    assert {seg["label"]: seg["value"] for seg in row["segments"]} == {"Post": 1, "Reel": 1}


@pytest.mark.django_db
def test_followers_history_drives_gain_and_line(insights_setup):
    from apps.social_accounts.models import FollowerSnapshot

    workspace, account, _ = insights_setup
    today = timezone.localdate()
    FollowerSnapshot.objects.create(social_account=account, date=today - timedelta(days=40), followers=21000)
    FollowerSnapshot.objects.create(social_account=account, date=today - timedelta(days=10), followers=21100)
    period = services.resolve_period(workspace, "30d")

    data = services.followers_by_channel(workspace, period)
    row = data["rows"][0]
    assert (row["start"], row["current"], row["gained"]) == (21000, 21200, 200)
    assert data["has_history"] is True
    assert [p["value"] for p in data["line"]["lines"][0]["points"]] == [21100, 21200]

    followers_card = services.summary(workspace, period)[1]
    assert followers_card["gained"] == 200


@pytest.mark.django_db
def test_health_check_records_daily_follower_snapshot(insights_setup):
    from unittest.mock import MagicMock, patch

    from apps.social_accounts.models import FollowerSnapshot
    from apps.social_accounts.tasks import check_social_account_health

    _, account, _ = insights_setup
    provider = MagicMock()
    provider.get_profile.return_value = MagicMock(follower_count=21250)
    with patch("providers.get_provider", return_value=provider):
        check_social_account_health.now(str(account.id))
        check_social_account_health.now(str(account.id))
    snapshots = FollowerSnapshot.objects.filter(social_account=account)
    assert snapshots.count() == 1 and snapshots.get().followers == 21250


@pytest.mark.django_db
def test_page_renders_new_sections(client, insights_setup):
    workspace, account, author = insights_setup
    _published(workspace, account, author, 1, "x", likes=3, comments=1, reach=10, interactions=4)
    body = client.get(reverse("insights:page", kwargs={"workspace_id": workspace.id})).content.decode()
    assert "Desempenho por canal" in body
    assert "Seguidores" in body and "Crescimento" in body
    assert "Posts enviados no período" in body
