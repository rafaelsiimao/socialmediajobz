"""Approval workflow business logic.

Editorial status now lives on ``PlatformPost`` so every social account flows
through the workflow independently. The functions in this module accept either
a ``Post`` (apply the action to *all* eligible children — the historical
"bundled" behaviour) or a single ``PlatformPost`` (per-account decision).

For the bundled case the resulting :class:`ApprovalAction` row stores
``platform_post=None``; for per-account decisions ``platform_post`` is set so
the audit trail remembers exactly which target was acted on.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.notifications.engine import notify
from apps.notifications.models import EventType

from .models import ApprovalAction, ApprovalReminder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_targets(target, *, eligible_from_states=None):
    """Normalise *target* into ``(post, [platform_posts], is_bundled)``.

    ``target`` may be a :class:`Post` (returns every child whose current state
    is in ``eligible_from_states``, or all children if not specified) or a
    :class:`PlatformPost` (returns just that one). Eligibility filtering keeps
    bundled actions from blowing up on already-published or already-approved
    siblings.
    """
    if isinstance(target, PlatformPost):
        return target.post, [target], False

    if not isinstance(target, Post):
        raise TypeError(f"Expected Post or PlatformPost, got {type(target).__name__}")

    children = list(target.platform_posts.select_related("social_account"))
    if eligible_from_states is not None:
        children = [pp for pp in children if pp.status in eligible_from_states]
    return target, children, True


def _transition_or_skip(pp, target_status):
    """Transition *pp* to *target_status*, returning True on success."""
    if pp.status == target_status:
        return True
    if not pp.can_transition_to(target_status):
        return False
    pp.transition_to(target_status)
    pp.save(update_fields=["status", "published_at", "updated_at"])
    return True


def _record_action(post, platform_post, user, action, comment=""):
    """Create an ApprovalAction row for either a bundled or per-PP action."""
    return ApprovalAction.objects.create(
        post=post,
        platform_post=platform_post,
        user=user,
        action=action,
        comment=comment,
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def submit_for_review(target, user, workspace, reviewer=None):
    """Submit a post (or single platform post) for internal review."""
    post, targets, is_bundled = _resolve_targets(
        target, eligible_from_states={"draft", "changes_requested", "rejected"}
    )

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "pending_review"):
                moved.append(pp)
        if not moved:
            return post

        if reviewer is not None:
            post.assigned_reviewer = reviewer
            post.save(update_fields=["assigned_reviewer", "updated_at"])

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.SUBMITTED)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.SUBMITTED)

        ApprovalReminder.objects.update_or_create(
            post=post,
            stage="pending_review",
            defaults={"reminder_count": 0, "last_reminder_at": None, "escalated": False},
        )

    app_url = getattr(settings, "APP_URL", "http://localhost:8000").rstrip("/")
    action_url = f"{app_url}{reverse('approvals:queue', kwargs={'workspace_id': workspace.id})}"

    # Notify designated reviewer or all reviewers with approve_posts permission
    target_reviewer = reviewer or post.assigned_reviewer
    if target_reviewer:
        if target_reviewer != user:
            notify(
                user=target_reviewer,
                event_type=EventType.POST_SUBMITTED,
                title="Publicação enviada para revisão",
                body=f'{user.display_name} enviou uma publicação para a sua revisão: "{post.caption_snippet}"',
                data={
                    "post_id": str(post.id),
                    "workspace_id": str(workspace.id),
                    "action_url": action_url,
                },
            )
    else:
        reviewers = WorkspaceMembership.objects.filter(workspace=workspace).select_related("user", "custom_role")
        for membership in reviewers:
            perms = membership.effective_permissions
            if perms.get("approve_posts", False) and membership.user != user:
                notify(
                    user=membership.user,
                    event_type=EventType.POST_SUBMITTED,
                    title="Publicação enviada para revisão",
                    body=f'{user.display_name} enviou uma publicação para a sua revisão: "{post.caption_snippet}"',
                    data={
                        "post_id": str(post.id),
                        "workspace_id": str(workspace.id),
                        "action_url": action_url,
                    },
                )

    return post


def approve_post(target, user, workspace, comment=""):
    """Approve a post or single platform post.

    If the workspace runs the two-stage internal+client flow and we're moving
    out of ``pending_review``, the target hops to ``approved`` and then to
    ``pending_client`` (the same behaviour as before, just per-target).
    """
    post, targets, is_bundled = _resolve_targets(
        target, eligible_from_states={"pending_review", "pending_client", "draft", "rejected", "changes_requested"}
    )

    two_stage = workspace.approval_workflow_mode == "required_internal_and_client"
    moved = []
    advanced_to_client = False
    with transaction.atomic():
        for pp in targets:
            from_pending_review = pp.status == "pending_review"
            if not _transition_or_skip(pp, "approved"):
                continue
            moved.append(pp)
            if two_stage and from_pending_review and _transition_or_skip(pp, "pending_client"):
                advanced_to_client = True
            elif not (two_stage and from_pending_review):
                target_dt = pp.scheduled_at or post.scheduled_at
                if target_dt:
                    if not pp.scheduled_at and post.scheduled_at:
                        pp.scheduled_at = post.scheduled_at
                        pp.save(update_fields=["scheduled_at"])
                    _transition_or_skip(pp, "scheduled")

        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.APPROVED, comment)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.APPROVED, comment)

        if advanced_to_client:
            ApprovalReminder.objects.update_or_create(
                post=post,
                stage="pending_client",
                defaults={"reminder_count": 0, "last_reminder_at": None, "escalated": False},
            )
            _notify_clients(post, workspace)

    if post.author and post.author != user:
        notify(
            user=post.author,
            event_type=EventType.POST_APPROVED,
            title="Publicação aprovada",
            body=f'Sua publicação "{post.caption_snippet}" foi aprovada por {user.display_name}.',
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )

    return post


def request_changes(target, user, workspace, comment):
    """Request changes on a post or single platform post. Comment is required."""
    if not comment.strip():
        raise ValueError("A comment is required when requesting changes.")

    post, targets, is_bundled = _resolve_targets(target, eligible_from_states={"pending_review", "pending_client"})

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "changes_requested"):
                moved.append(pp)
        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.CHANGES_REQUESTED, comment)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.CHANGES_REQUESTED, comment)

    if post.author and post.author != user:
        notify(
            user=post.author,
            event_type=EventType.POST_CHANGES_REQUESTED,
            title="Alterações solicitadas na sua publicação",
            body=f'{user.display_name} pediu alterações: "{comment[:100]}"',
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )

    return post


def reject_post(target, user, workspace, comment):
    """Reject a post or single platform post. Comment is required."""
    if not comment.strip():
        raise ValueError("A comment is required when rejecting a post.")

    post, targets, is_bundled = _resolve_targets(target, eligible_from_states={"pending_review", "pending_client"})

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "rejected"):
                moved.append(pp)
        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.REJECTED, comment)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.REJECTED, comment)

    if post.author and post.author != user:
        notify(
            user=post.author,
            event_type=EventType.POST_REJECTED,
            title="Publicação rejeitada",
            body=f'{user.display_name} rejeitou sua publicação: "{comment[:100]}"',
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )

    return post


def resubmit_post(target, user, workspace, reviewer=None):
    """Resubmit a post or single platform post after changes/rejection."""
    post, targets, is_bundled = _resolve_targets(target, eligible_from_states={"changes_requested", "rejected"})

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "pending_review"):
                moved.append(pp)
        if not moved:
            return post

        if reviewer is not None:
            post.assigned_reviewer = reviewer
            post.save(update_fields=["assigned_reviewer", "updated_at"])

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.RESUBMITTED)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.RESUBMITTED)

        ApprovalReminder.objects.update_or_create(
            post=post,
            stage="pending_review",
            defaults={"reminder_count": 0, "last_reminder_at": None, "escalated": False},
        )

    app_url = getattr(settings, "APP_URL", "http://localhost:8000").rstrip("/")
    action_url = f"{app_url}{reverse('approvals:queue', kwargs={'workspace_id': workspace.id})}"

    # Notify designated reviewer or all reviewers with approve_posts permission
    target_reviewer = reviewer or post.assigned_reviewer
    if target_reviewer:
        if target_reviewer != user:
            notify(
                user=target_reviewer,
                event_type=EventType.POST_SUBMITTED,
                title="Publicação reenviada para revisão",
                body=f'{user.display_name} reenviou uma publicação: "{post.caption_snippet}"',
                data={
                    "post_id": str(post.id),
                    "workspace_id": str(workspace.id),
                    "action_url": action_url,
                },
            )
    else:
        reviewers = WorkspaceMembership.objects.filter(workspace=workspace).select_related("user", "custom_role")
        for membership in reviewers:
            perms = membership.effective_permissions
            if perms.get("approve_posts", False) and membership.user != user:
                notify(
                    user=membership.user,
                    event_type=EventType.POST_SUBMITTED,
                    title="Publicação reenviada para revisão",
                    body=f'{user.display_name} reenviou uma publicação: "{post.caption_snippet}"',
                    data={
                        "post_id": str(post.id),
                        "workspace_id": str(workspace.id),
                        "action_url": action_url,
                    },
                )

    return post


def bulk_approve(post_ids, user, workspace):
    """Approve all eligible PlatformPosts under each post (bundled per post)."""
    results = []
    posts = Post.objects.filter(
        id__in=post_ids,
        workspace=workspace,
        platform_posts__status__in=["pending_review", "pending_client"],
    ).distinct()

    for post in posts:
        try:
            approve_post(post, user, workspace)
            results.append((str(post.id), True, None))
        except ValueError as e:
            results.append((str(post.id), False, str(e)))

    return results


def bulk_reject(post_ids, user, workspace, comment):
    """Reject all eligible PlatformPosts under each post (bundled per post)."""
    if not comment.strip():
        raise ValueError("A comment is required for bulk rejection.")

    results = []
    posts = Post.objects.filter(
        id__in=post_ids,
        workspace=workspace,
        platform_posts__status__in=["pending_review", "pending_client"],
    ).distinct()

    for post in posts:
        try:
            reject_post(post, user, workspace, comment)
            results.append((str(post.id), True, None))
        except ValueError as e:
            results.append((str(post.id), False, str(e)))

    return results


def _notify_clients(post, workspace):
    """Send CLIENT_APPROVAL_REQUESTED notification to all client members."""
    client_memberships = WorkspaceMembership.objects.filter(
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.CLIENT,
    ).select_related("user")

    for membership in client_memberships:
        notify(
            user=membership.user,
            event_type=EventType.CLIENT_APPROVAL_REQUESTED,
            title="Publicações prontas para sua revisão",
            body=f"Uma publicação em {workspace.name} está aguardando sua aprovação.",
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )
