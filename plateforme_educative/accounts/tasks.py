"""
Tâches Celery pour le module accounts.
- envoyer_email_task : envoi d'e-mail asynchrone (notifications, reset mot de passe)
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def envoyer_email_task(self, subject: str, text_content: str, html_content: str,
                       from_email: str, to_list: list):
    """
    Envoie un e-mail de manière asynchrone.

    Args:
        subject      : Sujet de l'e-mail.
        text_content : Corps en texte brut.
        html_content : Corps en HTML.
        from_email   : Adresse expéditrice.
        to_list      : Liste des destinataires.
    """
    from django.core.mail import EmailMultiAlternatives
    from accounts.models import ConfigurationSysteme

    # Vérifier le mode hors-ligne global
    config = ConfigurationSysteme.get_config()
    if config.mode_hors_ligne:
        logger.info(f"[Email] Envoi bloqué par la configuration Système (Mode Hors-Ligne activé) pour: {to_list}")
        return  # Annule silencieusement la tâche

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=to_list,
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        logger.info(f"[Email] E-mail envoyé avec succès à {to_list}")
    except Exception as exc:
        logger.error(f"[Email] Erreur d'envoi à {to_list} : {exc}", exc_info=True)
        raise self.retry(exc=exc)
