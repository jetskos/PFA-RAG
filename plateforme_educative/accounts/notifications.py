import logging
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import Notification

logger = logging.getLogger(__name__)


def notifier(destinataire, type, titre, message, url=None, envoyer_email=False):
    """
    Crée une notification en base de données pour le destinataire donné.
    Si envoyer_email est True, envoie également un e-mail à l'utilisateur
    de manière asynchrone via Celery.
    """
    try:
        # 1. Création de la notification en base de données
        notif = Notification.objects.create(
            destinataire=destinataire,
            type=type,
            titre=titre,
            message=message,
            url=url
        )
        logger.info(f"Notification créée en base pour {destinataire.email} (ID: {notif.id})")

        # 2. Envoi facultatif d'un e-mail (asynchrone via Celery)
        if envoyer_email and destinataire.email:
            try:
                subject = f"[EduTech] {titre}"
                context = {
                    'destinataire': destinataire,
                    'titre': titre,
                    'message': message,
                    'url': url,
                    'base_url': getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
                }

                html_content = render_to_string('accounts/emails/notification.html', context)
                text_content = strip_tags(html_content)

                from accounts.tasks import envoyer_email_task
                envoyer_email_task.delay(
                    subject=subject,
                    text_content=text_content,
                    html_content=html_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to_list=[destinataire.email],
                )
                logger.info(f"Tâche d'envoi d'e-mail planifiée pour {destinataire.email}")
            except Exception as mail_err:
                logger.error(
                    f"Erreur planification e-mail à {destinataire.email} : {mail_err}",
                    exc_info=True
                )

        return notif

    except Exception as e:
        logger.error(f"Erreur lors de la création de la notification : {e}", exc_info=True)
        return None
