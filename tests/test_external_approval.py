from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.approvals.external import issue_link, respond
from apps.approvals.models import ApprovalEmail, ApprovalLink
from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def external_post(user, organization, org_owner):
    ws = Workspace.objects.create(organization=organization, name="Cliente")
    WorkspaceMembership.objects.create(user=user, workspace=ws, workspace_role="owner")
    account = SocialAccount.objects.create(
        workspace=ws, platform="instagram", account_name="Cliente", account_platform_id="123"
    )
    post = Post.objects.create(workspace=ws, author=user, caption="Conteúdo público", internal_notes="SEGREDO INTERNO")
    PlatformPost.objects.create(post=post, social_account=account, platform_extra={"post_type": "reel"})
    return post


def make_link(post, user):
    return issue_link(post, user, "Cliente", "cliente@example.com")


@pytest.mark.django_db
def test_public_preview_does_not_login_or_consume(client, external_post, user):
    link, token = make_link(external_post, user)
    response = client.get(reverse("public_approval", args=[token]))
    assert response.status_code == 200
    assert b"SEGREDO INTERNO" not in response.content
    assert "Conteúdo público" in response.content.decode()
    assert "_auth_user_id" not in client.session
    link.refresh_from_db()
    assert link.responded_at is None
    assert link.expires_at > timezone.now() + timedelta(days=6)
    assert token != link.token_hash


@pytest.mark.django_db
@pytest.mark.parametrize(
    "decision,comment,status",
    [
        ("approved", "", "approved"),
        ("rejected", "Não publicar", "rejected"),
        ("changes_requested", "Trocar a capa", "changes_requested"),
    ],
)
def test_decision_is_once_and_queues_result(external_post, user, decision, comment, status):
    link, token = make_link(external_post, user)
    respond(token, decision, comment)
    assert external_post.platform_posts.get().status == status
    assert external_post.approval_actions.filter(action=decision, user=None).count() == 1
    email = ApprovalEmail.objects.get(link=link, kind="result")
    assert email.recipient == "rafael.simao@jobz.com.br"
    assert "Cliente" in email.body
    with pytest.raises(ValueError):
        respond(token, "approved", "")
    assert ApprovalEmail.objects.filter(link=link, kind="result").count() == 1


@pytest.mark.django_db
def test_expiry_replacement_and_edit_invalidate(client, external_post, user):
    old, old_token = make_link(external_post, user)
    new, token = make_link(external_post, user)
    assert client.get(reverse("public_approval", args=[old_token])).status_code == 410
    external_post.caption = "Mudou"
    external_post.save()
    assert client.post(reverse("public_approval", args=[token]), {"decision": "approved"}).status_code == 410
    assert external_post.platform_posts.get().status == "pending_client"
    external_post.caption = "Conteúdo público"
    external_post.save()
    ApprovalLink.objects.filter(pk=new.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(ValueError):
        respond(token, "approved", "")


@pytest.mark.django_db
def test_validation_and_thanks(client, external_post, user):
    link, token = make_link(external_post, user)
    url = reverse("public_approval", args=[token])
    assert client.post(url, {"decision": "changes_requested", "comment": " "}).status_code == 400
    assert client.post(url, {"decision": "delete"}).status_code == 400
    response = client.post(url, {"decision": "approved"})
    assert response.status_code == 302
    thanks = client.get(response.url)
    assert "Obrigado" in thanks.content.decode()
    assert b"10000" in thanks.content
    assert client.get(url).status_code == 410


@pytest.mark.django_db
def test_mail_failure_is_persisted_and_retryable(external_post, user):
    from apps.approvals.tasks import deliver_approval_email

    link, token = make_link(external_post, user)
    email = ApprovalEmail.objects.get(link=link, kind="invitation")
    with (
        patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("SMTP offline")),
        pytest.raises(OSError),
    ):
        deliver_approval_email.now(str(email.pk))
    email.refresh_from_db()
    assert email.attempts == 1
    assert email.sent_at is None
    assert email.error
    with patch("django.core.mail.EmailMultiAlternatives.send", return_value=1) as send:
        deliver_approval_email.now(str(email.pk))
        deliver_approval_email.now(str(email.pk))
    assert send.call_count == 1
    email.refresh_from_db()
    assert email.sent_at


@pytest.mark.django_db
def test_composer_creates_link_and_copy_screen(client, external_post, user):
    client.force_login(user)
    url = reverse(
        "composer:save_post_edit", kwargs={"workspace_id": external_post.workspace_id, "post_id": external_post.pk}
    )
    with patch("apps.approvals.tasks.deliver_approval_email"):
        response = client.post(
            url,
            {
                "action": "external_approval",
                "caption": "Conteúdo aprovado pelo cliente",
                "selected_accounts": str(external_post.platform_posts.get().social_account_id),
                "approval_name": "Luciana",
                "approval_email": "luciana@example.com",
            },
            HTTP_HX_REQUEST="true",
        )
    assert response.status_code == 204
    assert "HX-Redirect" in response
    details = client.get(response["HX-Redirect"])
    assert details.status_code == 200
    assert "Copiar link" in details.content.decode()
    link = ApprovalLink.objects.get(post=external_post)
    token = client.session[f"approval_link_{link.pk}"]
    client.logout()
    preview = client.get(reverse("public_approval", args=[token]))
    assert preview.status_code == 200
    assert "Conteúdo aprovado pelo cliente" in preview.content.decode()
    assert "luciana@example.com" not in preview.content.decode()


@pytest.mark.django_db
def test_public_post_requires_csrf(external_post, user):
    from django.test import Client

    link, token = make_link(external_post, user)
    browser = Client(enforce_csrf_checks=True)
    url = reverse("public_approval", args=[token])
    assert browser.post(url, {"decision": "approved"}).status_code == 403
    page = browser.get(url)
    assert page.status_code == 200
    csrf = browser.cookies["csrftoken"].value
    assert browser.post(url, {"decision": "approved", "csrfmiddlewaretoken": csrf}).status_code == 302


@pytest.mark.django_db
def test_issuing_requires_permission_and_does_not_touch_scheduled_post(external_post, user):
    from django.core.exceptions import PermissionDenied

    membership = WorkspaceMembership.objects.get(user=user, workspace=external_post.workspace)
    membership.workspace_role = "contributor"
    membership.save()
    with pytest.raises(PermissionDenied):
        make_link(external_post, user)
    membership.workspace_role = "owner"
    membership.save()
    external_post.platform_posts.update(status="scheduled")
    with pytest.raises(ValueError):
        make_link(external_post, user)
    assert external_post.platform_posts.get().status == "scheduled"
    assert not ApprovalLink.objects.exists()


@pytest.mark.django_db
def test_details_cannot_be_accessed_from_other_workspace(client, external_post, user, organization):
    link, token = make_link(external_post, user)
    other = Workspace.objects.create(organization=organization, name="Outro cliente")
    WorkspaceMembership.objects.create(user=user, workspace=other, workspace_role="owner")
    client.force_login(user)
    response = client.get(reverse("approvals:link_details", kwargs={"workspace_id": other.pk, "link_id": link.pk}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_preview_renders_images_video_and_platform_override(client, external_post, user, organization):
    from apps.composer.models import PostMedia
    from apps.media_library.models import MediaAsset

    image = MediaAsset.objects.create(
        organization=organization,
        workspace=external_post.workspace,
        uploaded_by=user,
        filename="slide.jpg",
        file="tests/slide.jpg",
        media_type="image",
        mime_type="image/jpeg",
        file_size=12,
    )
    video = MediaAsset.objects.create(
        organization=organization,
        workspace=external_post.workspace,
        uploaded_by=user,
        filename="reel.mp4",
        file="tests/reel.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size=12,
    )
    PostMedia.objects.create(post=external_post, media_asset=image, position=0)
    PostMedia.objects.create(post=external_post, media_asset=video, position=1)
    external_post.platform_posts.update(platform_specific_caption="Legenda do canal")
    link, token = make_link(external_post, user)
    html = client.get(reverse("public_approval", args=[token])).content.decode()
    assert "slide.jpg" in html and "reel.mp4" in html
    assert "controls playsinline" in html
    assert "Legenda do canal" in html
    assert "Conteúdo público" not in html


@pytest.mark.django_db
def test_result_notification_and_background_job(external_post, user):
    from django.contrib.auth import get_user_model

    from apps.notifications.models import Notification

    rafael = get_user_model().objects.create_user(email="rafael.simao@jobz.com.br", password="test123")
    with patch("apps.approvals.tasks.deliver_approval_email") as enqueue:
        from django.test import TestCase

        with TestCase.captureOnCommitCallbacks(execute=True):
            link, token = make_link(external_post, user)
            respond(token, "changes_requested", "Revisar vídeo")
        assert enqueue.call_count == 2
    notice = Notification.objects.get(user=rafael, event_type="post_changes_requested")
    assert "Revisar vídeo" in notice.body


@pytest.mark.django_db
def test_canceled_invitation_is_not_sent(external_post, user):
    from apps.approvals.tasks import deliver_approval_email

    link, token = make_link(external_post, user)
    make_link(external_post, user)
    email = link.emails.get(kind="invitation")
    with patch("django.core.mail.EmailMultiAlternatives.send") as send:
        deliver_approval_email.now(str(email.pk))
    assert not send.called


@pytest.mark.django_db
def test_unchanged_autosave_keeps_link_and_real_edit_permanently_revokes(client, external_post, user):
    link, token = make_link(external_post, user)
    client.force_login(user)
    url = reverse(
        "composer:autosave_edit", kwargs={"workspace_id": external_post.workspace_id, "post_id": external_post.pk}
    )
    data = {
        "caption": external_post.caption,
        "selected_accounts": str(external_post.platform_posts.get().social_account_id),
        f"ig_format_{external_post.platform_posts.get().social_account_id}": "reel",
    }
    assert client.post(url, data).status_code == 200
    assert client.get(reverse("public_approval", args=[token])).status_code == 200
    assert client.post(url, {**data, "caption": "Novo conteúdo"}).status_code == 200
    link.refresh_from_db()
    assert link.revoked_at is not None
    client.post(url, data)
    assert client.get(reverse("public_approval", args=[token])).status_code == 410


@pytest.mark.django_db
def test_approval_preserves_existing_schedule(external_post, user):
    external_post.scheduled_at = timezone.now() + timedelta(days=2)
    external_post.save()
    link, token = make_link(external_post, user)
    respond(token, "approved", "Pode publicar")
    pp = external_post.platform_posts.get()
    assert pp.status == "scheduled"
    assert pp.scheduled_at == external_post.scheduled_at


@pytest.mark.django_db
def test_editor_cannot_issue_external_link_via_composer(client, external_post, user):
    WorkspaceMembership.objects.filter(user=user, workspace=external_post.workspace).update(workspace_role="editor")
    client.force_login(user)
    response = client.post(
        reverse(
            "composer:save_post_edit", kwargs={"workspace_id": external_post.workspace_id, "post_id": external_post.pk}
        ),
        {
            "action": "external_approval",
            "approval_name": "Cliente",
            "approval_email": "cliente@example.com",
        },
    )
    assert response.status_code == 403
    assert not ApprovalLink.objects.exists()


@pytest.mark.django_db
def test_invitation_job_is_persisted_with_link(external_post, user):
    from background_task.models import Task

    link, token = make_link(external_post, user)
    email = link.emails.get(kind="invitation")
    assert Task.objects.filter(
        task_name="apps.approvals.email_tasks.deliver_approval_email", task_params__contains=str(email.pk)
    ).exists()


@pytest.mark.django_db
def test_composer_offers_link_and_previous_delivery(client, external_post, user):
    link, token = make_link(external_post, user)
    client.force_login(user)
    response = client.get(
        reverse(
            "composer:compose_edit", kwargs={"workspace_id": external_post.workspace_id, "post_id": external_post.pk}
        )
    )
    assert response.status_code == 200
    assert "Aprovação por link" in response.content.decode()
    assert "Ver link e envio" in response.content.decode()
    assert b'id="approval-email"' in response.content


@pytest.mark.django_db
def test_schedule_timezone_representation_does_not_change_content_hash(external_post):
    from zoneinfo import ZoneInfo

    from apps.approvals.external import content_revision

    external_post.scheduled_at = (timezone.now() + timedelta(days=2)).astimezone(ZoneInfo("America/Sao_Paulo"))
    external_post.save()
    before_reload = content_revision(external_post)
    external_post.refresh_from_db()
    assert content_revision(external_post) == before_reload


@pytest.mark.django_db
@pytest.mark.parametrize("decision", ["approved", "rejected", "changes_requested"])
def test_https_form_preserves_same_origin_for_csrf(external_post, user, decision):
    from django.test import Client

    link, token = make_link(external_post, user)
    browser = Client(enforce_csrf_checks=True)
    url = reverse("public_approval", args=[token])
    page = browser.get(url, secure=True)
    assert page["Referrer-Policy"] == "same-origin"
    assert b'<meta name="referrer" content="same-origin">' in page.content
    csrf = browser.cookies["csrftoken"].value
    data = {"decision": decision, "comment": "Ajustar o vídeo", "csrfmiddlewaretoken": csrf}
    # Correct token alone must not accept a foreign or opaque Origin.
    assert browser.post(url, data, secure=True, HTTP_ORIGIN="https://outro-site.example").status_code == 403
    assert browser.post(url, data, secure=True, HTTP_ORIGIN="null").status_code == 403
    response = browser.post(
        url, data, secure=True, HTTP_ORIGIN="https://testserver", HTTP_REFERER=f"https://testserver{url}"
    )
    assert response.status_code == 302
    link.refresh_from_db()
    assert link.decision == decision
