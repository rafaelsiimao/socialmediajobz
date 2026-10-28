"""Public approval capabilities; never create a login session for recipients."""

import hashlib
import json
import secrets
from datetime import UTC, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from apps.composer.models import Post
from apps.members.models import WorkspaceMembership

from .models import ApprovalAction, ApprovalEmail, ApprovalLink

DECISIONS = {"approved": "Aprovado", "rejected": "Rejeitado", "changes_requested": "Precisa de ajustes"}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def content_revision(post):
    """Hash editorial content, not volatile URLs, metrics or workflow status."""
    data = {
        "title": post.title,
        "caption": post.caption,
        "first_comment": post.first_comment,
        "scheduled_at": post.scheduled_at.astimezone(UTC).isoformat() if post.scheduled_at else None,
        "media": list(
            post.media_attachments.order_by("position", "id").values(
                "media_asset_id", "media_asset__file", "media_asset__updated_at", "position", "alt_text"
            )
        ),
        "channels": list(
            post.platform_posts.order_by("id").values(
                "id",
                "social_account_id",
                "platform_specific_title",
                "platform_specific_caption",
                "platform_specific_first_comment",
                "platform_specific_media",
                "platform_extra",
                "scheduled_at",
            )
        ),
    }
    return digest(json.dumps(data, sort_keys=True, default=str))


def invalidate_changed_links(post):
    active = ApprovalLink.objects.filter(post=post, responded_at=None, revoked_at=None)
    if active.exists():
        active.exclude(content_hash=content_revision(post)).update(revoked_at=timezone.now())


def ensure_valid(link):
    if (
        link.revoked_at
        or link.responded_at
        or link.expires_at <= timezone.now()
        or link.post.workspace.is_archived
        or content_revision(link.post) != link.content_hash
    ):
        raise ValueError("Este link foi encerrado, expirou ou a publicação foi alterada. Solicite um novo link.")
    children = list(link.post.platform_posts.all())
    if not children or any(pp.status != "pending_client" for pp in children):
        raise ValueError("Esta solicitação de aprovação já foi encerrada.")


def queue_email(link, kind, recipient, subject, body):
    email = ApprovalEmail.objects.create(link=link, kind=kind, recipient=recipient, subject=subject[:255], body=body)
    from .tasks import deliver_approval_email

    # The decorator only inserts a job in this same database transaction.
    # The worker cannot read the job until the link/decision has committed.
    deliver_approval_email(str(email.pk))
    return email


def issue_link(post, user, name, email):
    name, email = name.strip(), email.strip()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValueError("Informe um e-mail válido para o cliente.") from exc
    if not name or len(name) > 150 or len(email) > 254:
        raise ValueError("Informe o nome do cliente (até 150 caracteres) e um e-mail válido.")
    membership = (
        WorkspaceMembership.objects.filter(user=user, workspace=post.workspace).select_related("custom_role").first()
    )
    if not membership or not membership.effective_permissions.get("approve_posts"):
        raise PermissionDenied("Você não pode enviar publicações para aprovação externa.")
    token = secrets.token_urlsafe(48)
    with transaction.atomic():
        post = Post.objects.select_for_update().get(pk=post.pk)
        targets = list(post.platform_posts.select_for_update().order_by("pk"))
        if not targets or any(
            pp.status not in {"draft", "pending_review", "approved", "pending_client", "changes_requested", "rejected"}
            for pp in targets
        ):
            raise ValueError(
                "Salve como rascunho antes de enviar. Publicações agendadas ou publicadas não podem ser enviadas."
            )
        ApprovalLink.objects.filter(post=post, revoked_at=None, responded_at=None).update(revoked_at=timezone.now())
        for pp in targets:
            # Explicit external review initiated by an authorized approver.
            pp.status = "pending_client"
            pp.save(update_fields=["status", "updated_at"])
        link = ApprovalLink.objects.create(
            post=post,
            created_by=user,
            token_hash=digest(token),
            recipient_name=name,
            recipient_email=email,
            content_hash=content_revision(post),
            expires_at=timezone.now() + timedelta(days=7),
        )
        ApprovalAction.objects.create(
            post=post, user=user, action="submitted", comment=f"Aprovação externa solicitada a {name} <{email}>."
        )
        url = settings.APP_URL.rstrip("/") + reverse("public_approval", args=[token])
        queue_email(
            link,
            "invitation",
            email,
            f"{post.workspace.name}: publicação para aprovação",
            f"Olá, {name}!\n\nRevise a publicação de {post.workspace.name}:\n{url}\n\n"
            "Você pode aprovar, rejeitar ou solicitar ajustes, sem login. O link é pessoal, permite uma resposta e vale por 7 dias. Não encaminhe a terceiros.",
        )
    return link, token


def respond(token, decision, comment):
    if decision not in DECISIONS:
        raise ValidationError("Escolha uma das três opções de resposta.")
    comment = comment.strip()
    if len(comment) > 10000:
        raise ValidationError("O comentário deve ter até 10.000 caracteres.")
    if decision != "approved" and not comment:
        raise ValidationError("Descreva o motivo da rejeição ou os ajustes necessários.")
    with transaction.atomic():
        # Lock order is always Post → PlatformPosts → ApprovalLink, including reissue.
        candidate = ApprovalLink.objects.only("post_id").get(token_hash=digest(token))
        post = Post.objects.select_for_update().get(pk=candidate.post_id)
        targets = list(post.platform_posts.select_for_update().order_by("pk"))
        link = ApprovalLink.objects.select_for_update().select_related("post__workspace").get(pk=candidate.pk)
        ensure_valid(link)
        for pp in targets:
            pp.transition_to(decision)
            if decision == "approved" and (pp.scheduled_at or post.scheduled_at):
                pp.scheduled_at = pp.scheduled_at or post.scheduled_at
                pp.transition_to("scheduled")
            pp.save(update_fields=["status", "scheduled_at", "updated_at"])
        link.responded_at = timezone.now()
        link.decision, link.comment = decision, comment
        link.save(update_fields=["responded_at", "decision", "comment"])
        ApprovalAction.objects.create(
            post=post,
            user=None,
            action=decision,
            comment=f"Resposta por link — {link.recipient_name} <{link.recipient_email}>\n{comment}",
        )
        edit_url = settings.APP_URL.rstrip("/") + reverse(
            "composer:compose_edit", kwargs={"workspace_id": post.workspace_id, "post_id": post.pk}
        )
        recipient = getattr(settings, "APPROVAL_RESULT_EMAIL", "rafael.simao@jobz.com.br")
        title = f"{DECISIONS[decision]} — {post.workspace.name}"[:255]
        body = (
            f"Cliente: {link.recipient_name} <{link.recipient_email}>\nWorkspace: {post.workspace.name}\n"
            f"Resultado: {DECISIONS[decision]}\nPublicação: {post.caption_snippet}\nComentários: {comment or 'Sem comentários'}\n\n{edit_url}"
        )
        queue_email(link, "result", recipient, title, body)
        from django.contrib.auth import get_user_model

        from apps.notifications.models import Notification

        rafael = get_user_model().objects.filter(email__iexact=recipient, is_active=True).first()
        if rafael:
            Notification.objects.create(
                user=rafael,
                event_type=f"post_{decision}",
                title=title,
                body=body,
                data={"post_id": str(post.pk), "workspace_id": str(post.workspace_id), "action_url": edit_url},
            )
    return link


def preview_channels(post):
    from apps.media_library.models import MediaAsset

    attachments = list(post.media_attachments.select_related("media_asset").order_by("position", "id"))
    channels = []
    for pp in post.platform_posts.select_related("social_account").order_by("id"):
        assets = [a.media_asset for a in attachments]
        if pp.platform_specific_media is not None:
            allowed = MediaAsset.objects.filter(organization=post.workspace.organization).filter(
                models.Q(workspace=post.workspace) | models.Q(workspace__isnull=True)
            )
            by_id = {str(a.pk): a for a in allowed.filter(pk__in=pp.platform_specific_media)}
            assets = [by_id[str(pk)] for pk in pp.platform_specific_media if str(pk) in by_id]
        channels.append(
            {
                "account": pp.social_account,
                "caption": pp.effective_caption,
                "title": "" if pp.is_instagram_story else pp.effective_title,
                "first_comment": pp.effective_first_comment,
                "media": assets,
                "format": (pp.platform_extra or {}).get("post_type", "feed"),
                "collaborators": (pp.platform_extra or {}).get("collaborators", []),
            }
        )
    return channels
