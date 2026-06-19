import logging
from .models import JournalAudit

logger = logging.getLogger(__name__)

def journaliser(request, action, objet, detail=None):
    """
    Enregistre une action sensible dans le journal d'audit de manière asynchrone et résiliente.
    """
    try:
        # 1. Extraction de l'adresse IP
        ip = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')

        # 2. Extraction de l'utilisateur
        user = None
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user

        # 3. Extraction des informations de l'objet
        type_objet = ""
        id_objet = None
        representation = ""

        if objet is not None:
            if isinstance(objet, str):
                type_objet = "Manuel"
                representation = objet
            else:
                type_objet = objet.__class__.__name__
                if hasattr(objet, 'pk'):
                    id_objet = str(objet.pk)
                representation = str(objet)

        # 4. Enregistrement
        JournalAudit.objects.create(
            utilisateur=user,
            action=action,
            type_objet=type_objet,
            id_objet=id_objet,
            representation=representation,
            details=detail,
            adresse_ip=ip
        )
    except Exception as e:
        logger.error(f"Échec de l'enregistrement dans le journal d'audit : {e}", exc_info=True)
