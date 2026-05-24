from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_notification(to: str, subject: str, body: str) -> bool:
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            fail_silently=False,
        )
        logger.info(f"Notificación enviada a {to} | Asunto: {subject}")
        return True
    except Exception as e:
        logger.error(f"Fallo al enviar notificación a {to} | Asunto: {subject} | Error: {e}")
        from notifications.models import FailedNotification
        FailedNotification.objects.create(
            to=to,
            subject=subject,
            body=body,
            error_message=str(e),
        )
        raise