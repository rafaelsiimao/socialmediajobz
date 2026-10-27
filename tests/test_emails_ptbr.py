import pytest
from django.core import mail
from django.urls import reverse

from apps.notifications.email_preview import _sample_contexts

PREVIEWS = list(_sample_contexts())


@pytest.fixture
def staff_client(client, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client.force_login(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("name", PREVIEWS)
def test_every_email_is_jobz_branded_and_in_portuguese(staff_client, name):
    html = staff_client.get(reverse("notifications:email_preview", kwargs={"name": name})).content.decode()
    text = staff_client.get(
        reverse("notifications:email_preview", kwargs={"name": name}), {"format": "txt"}
    ).content.decode()

    for body in (html, text):
        assert "Brightbean" not in body
        assert "Jobz" in body
    assert "jobz-logo-preto" in html
    assert "#1E81FE" in html  # Jobz blue button
    assert 'lang="pt-BR"' in html
    for english in ("View Details", "Accept Invitation", "Review Posts", "Connect Accounts", "Manage preferences"):
        assert english not in html


@pytest.mark.django_db
def test_email_preview_is_staff_only(client, user):
    client.force_login(user)
    assert client.get(reverse("notifications:email_preview_index")).status_code == 403


@pytest.mark.django_db
def test_notification_email_is_sent_in_portuguese(user, settings):
    from apps.notifications.engine import _dispatch_email
    from apps.notifications.models import Notification, NotificationDelivery

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    notification = Notification.objects.create(
        user=user,
        event_type="post_approved",
        title="Publicação aprovada",
        body="Sua publicação foi aprovada.",
        data={"action_url": "https://example.com/post"},
    )
    delivery = NotificationDelivery.objects.create(notification=notification, channel="email")

    _dispatch_email(delivery)

    sent = mail.outbox[-1]
    assert sent.subject == "Publicação aprovada"
    html = sent.alternatives[0][0]
    assert "Ver detalhes" in html and "jobz-logo-preto" in html
    assert "Gerenciar preferências" in sent.body


@pytest.mark.django_db
def test_password_reset_email_is_in_portuguese(client, user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client.post(reverse("account_reset_password"), {"email": user.email})

    sent = mail.outbox[-1]
    assert sent.subject.startswith("[Jobz Social Media]")
    assert "senha" in sent.subject.lower() or "senha" in sent.body.lower()
    assert "Jobz Social Media" in sent.body
    html = sent.alternatives[0][0]
    assert "Criar nova senha" in html


@pytest.mark.django_db
def test_approval_notification_titles_are_portuguese():
    from pathlib import Path

    source = Path("apps/approvals/services.py").read_text(encoding="utf-8")
    assert "Post submitted for review" not in source
    assert "Publicação enviada para revisão" in source
