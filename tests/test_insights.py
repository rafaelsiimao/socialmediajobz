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
