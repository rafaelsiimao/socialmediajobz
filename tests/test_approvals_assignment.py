import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string

from apps.approvals.models import ApprovalAction
from apps.approvals.services import resubmit_post, submit_for_review
from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.notifications.models import EventType, Notification
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

User = get_user_model()


@pytest.fixture
def org_and_workspace(db):
    org = Organization.objects.create(name="Test Org")
    workspace = Workspace.objects.create(
        organization=org,
        name="Test Workspace",
        approval_workflow_mode="required_internal",
    )
    return org, workspace


@pytest.fixture
def users_and_memberships(db, org_and_workspace):
    org, workspace = org_and_workspace
    author = User.objects.create_user(email="author@example.com", password="password123", name="Author")
    reviewer1 = User.objects.create_user(email="reviewer1@example.com", password="password123", name="Reviewer One")
    reviewer2 = User.objects.create_user(email="reviewer2@example.com", password="password123", name="Reviewer Two")

    # Author is contributor
    WorkspaceMembership.objects.create(
        user=author,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.CONTRIBUTOR,
    )
    # Reviewer 1 is manager (has approve_posts=True)
    WorkspaceMembership.objects.create(
        user=reviewer1,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.MANAGER,
    )
    # Reviewer 2 is owner (has approve_posts=True)
    WorkspaceMembership.objects.create(
        user=reviewer2,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
    )

    return author, reviewer1, reviewer2


@pytest.fixture
def sample_post(db, org_and_workspace, users_and_memberships):
    org, workspace = org_and_workspace
    author, _, _ = users_and_memberships

    sa = SocialAccount.objects.create(
        workspace=workspace,
        platform="facebook",
        account_platform_id="fb-123",
        account_name="Facebook Page",
    )

    post = Post.objects.create(
        workspace=workspace,
        author=author,
        caption="Launch of Jobz Social Media!",
    )
    pp = PlatformPost.objects.create(
        post=post,
        social_account=sa,
        status="draft",
    )
    return post, pp


@pytest.mark.django_db
def test_submit_for_review_with_specific_reviewer(org_and_workspace, users_and_memberships, sample_post):
    _, workspace = org_and_workspace
    author, reviewer1, reviewer2 = users_and_memberships
    post, pp = sample_post

    # Submit specifically for reviewer1
    submit_for_review(post, author, workspace, reviewer=reviewer1)

    post.refresh_from_db()
    pp.refresh_from_db()

    assert post.assigned_reviewer == reviewer1
    assert pp.status == "pending_review"

    # Only reviewer1 should receive notification
    notifs_r1 = Notification.objects.filter(user=reviewer1, event_type=EventType.POST_SUBMITTED)
    notifs_r2 = Notification.objects.filter(user=reviewer2, event_type=EventType.POST_SUBMITTED)
    notifs_author = Notification.objects.filter(user=author, event_type=EventType.POST_SUBMITTED)

    assert notifs_r1.count() == 1
    assert notifs_r2.count() == 0
    assert notifs_author.count() == 0

    notif = notifs_r1.first()
    assert "action_url" in notif.data
    assert f"/workspace/{workspace.id}/approvals/" in notif.data["action_url"]


@pytest.mark.django_db
def test_submit_for_review_without_specific_reviewer(org_and_workspace, users_and_memberships, sample_post):
    _, workspace = org_and_workspace
    author, reviewer1, reviewer2 = users_and_memberships
    post, pp = sample_post

    # Submit with reviewer=None (general fallback)
    submit_for_review(post, author, workspace, reviewer=None)

    post.refresh_from_db()
    pp.refresh_from_db()

    assert post.assigned_reviewer is None
    assert pp.status == "pending_review"

    # Both reviewers should be notified, author shouldn't
    assert Notification.objects.filter(user=reviewer1, event_type=EventType.POST_SUBMITTED).count() == 1
    assert Notification.objects.filter(user=reviewer2, event_type=EventType.POST_SUBMITTED).count() == 1
    assert Notification.objects.filter(user=author, event_type=EventType.POST_SUBMITTED).count() == 0


@pytest.mark.django_db
def test_resubmit_remembers_assigned_reviewer(org_and_workspace, users_and_memberships, sample_post):
    _, workspace = org_and_workspace
    author, reviewer1, reviewer2 = users_and_memberships
    post, pp = sample_post

    # Initially assigned to reviewer1
    submit_for_review(post, author, workspace, reviewer=reviewer1)
    pp.status = "changes_requested"
    pp.save()
    Notification.objects.all().delete()

    # Resubmit without explicitly passing reviewer - should use post.assigned_reviewer
    resubmit_post(post, author, workspace)

    assert Notification.objects.filter(user=reviewer1, event_type=EventType.POST_SUBMITTED).count() == 1
    assert Notification.objects.filter(user=reviewer2, event_type=EventType.POST_SUBMITTED).count() == 0


@pytest.mark.django_db
def test_notification_email_template_contains_action_url(users_and_memberships):
    _, reviewer1, _ = users_and_memberships
    notif = Notification.objects.create(
        user=reviewer1,
        event_type=EventType.POST_SUBMITTED,
        title="Post submitted for review",
        body="Author submitted a post for your review",
        data={"action_url": "https://socialmedia-web.hqzarv.easypanel.host/workspace/test/approvals/"},
    )

    rendered_html = render_to_string(
        "notifications/email/notification.html",
        {"notification": notif, "user": reviewer1, "app_url": "https://socialmedia-web.hqzarv.easypanel.host"},
    )
    assert "https://socialmedia-web.hqzarv.easypanel.host/workspace/test/approvals/" in rendered_html
    assert "View Details" in rendered_html
