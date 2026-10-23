import zoneinfo
from datetime import datetime, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.calendar.models import PostingSlot
from apps.composer.models import Post
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def queue_setup(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Queue workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    account = SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-q",
        account_name="Jobz IG",
        connection_status="connected",
    )
    for day in range(7):
        PostingSlot.objects.create(social_account=account, day_of_week=day, time=time(10, 0))
    client.force_login(org_owner)
    return workspace, account


def _next_slot(workspace):
    tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
    now = timezone.now().astimezone(tz)
    candidate = datetime.combine(now.date(), time(10, 0), tzinfo=tz)
    return candidate if candidate > now else candidate + timedelta(days=1)


@pytest.mark.django_db
def test_queue_lists_free_slots_with_prefilled_new_link(client, queue_setup):
    workspace, account = queue_setup
    body = client.get(reverse("calendar:publish_tab_queue", kwargs={"workspace_id": workspace.id})).content.decode()

    slot = _next_slot(workspace)
    assert body.count(">10:00<") + body.count("10:00</div>") >= 7
    assert f"account={account.id}&scheduled_date={slot:%Y-%m-%d}&scheduled_time=10:00" in body
    assert "Novo" in body
    assert "Mais horários" in body


@pytest.mark.django_db
def test_scheduled_post_takes_the_place_of_its_slot(client, queue_setup, org_owner):
    workspace, account = queue_setup
    slot = _next_slot(workspace)
    post = Post.objects.create(workspace=workspace, author=org_owner, caption="Agendado", scheduled_at=slot)
    post.platform_posts.create(social_account=account, status="scheduled")

    body = client.get(reverse("calendar:publish_tab_queue", kwargs={"workspace_id": workspace.id})).content.decode()

    assert "Agendado" in body
    assert f"scheduled_date={slot:%Y-%m-%d}&scheduled_time=10:00" not in body


@pytest.mark.django_db
def test_more_slots_extends_the_horizon(client, queue_setup):
    workspace, account = queue_setup
    url = reverse("calendar:publish_tab_queue", kwargs={"workspace_id": workspace.id})
    week = client.get(url).content.decode().count("scheduled_time=10:00")
    two_weeks = client.get(url, {"days": 14}).content.decode().count("scheduled_time=10:00")
    capped = client.get(url, {"days": 999}).content.decode()
    assert two_weeks == week + 7
    assert "Mais horários" not in capped


@pytest.mark.django_db
def test_new_post_from_slot_preselects_account(client, queue_setup):
    workspace, account = queue_setup
    response = client.get(
        reverse("composer:compose", kwargs={"workspace_id": workspace.id}),
        {"account": str(account.id), "scheduled_date": "2026-10-30", "scheduled_time": "10:00"},
    )
    assert response.status_code == 200
    assert response.context["selected_account_ids"] == [str(account.id)]

    invalid = client.get(reverse("composer:compose", kwargs={"workspace_id": workspace.id}), {"account": "not-a-uuid"})
    assert invalid.status_code == 200
    assert invalid.context["selected_account_ids"] == []
