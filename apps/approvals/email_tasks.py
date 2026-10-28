from background_task import background
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from .models import ApprovalEmail


@background(schedule=0)
def deliver_approval_email(email_id):
    """Worker retries exceptions; successful sends are never deliberately repeated."""
    failure = None
    with transaction.atomic():
        email = ApprovalEmail.objects.select_for_update().select_related("link__post__workspace").get(pk=email_id)
        if email.sent_at:
            return
        if email.kind == "invitation":
            from .external import ensure_valid

            try:
                ensure_valid(email.link)
            except ValueError:
                email.error = "Convite cancelado: link encerrado ou conteúdo alterado."
                email.save(update_fields=["error"])
                return
        email.attempts += 1
        try:
            count = EmailMultiAlternatives(
                subject=email.subject, body=email.body, from_email=settings.DEFAULT_FROM_EMAIL, to=[email.recipient]
            ).send(fail_silently=False)
            if count != 1:
                raise OSError("O servidor de e-mail não confirmou o envio.")
            email.sent_at = timezone.now()
            email.error = ""
        except Exception as exc:
            email.error = str(exc)[:1000]
            failure = exc
        email.save(update_fields=["attempts", "sent_at", "error"])
    if failure:
        raise failure
