"""Service des fichiers /media/ derrière l'authentification.

`django.views.static.serve` ne fait aucun contrôle d'accès : sans ce wrapper,
tout le contenu de MEDIA_ROOT (supports de cours, vidéos, ZIP d'export, base
vectorielle ChromaDB, boîte satellite…) est téléchargeable par n'importe qui
connaissant l'URL. La plateforme étant fermée (le catalogue exige déjà une
connexion), on impose simplement `login_required` et on interdit les dossiers
purement internes.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.views.static import serve

# Dossiers sous MEDIA_ROOT qui ne doivent jamais être servis par HTTP,
# même à un utilisateur connecté (données internes / autres utilisateurs).
_BLOCKED_PREFIXES = ('chroma_db/', 'imports/', 'satellite_inbox/')


@login_required
def serve_protected_media(request, path):
    normalized = path.replace('\\', '/').lstrip('/')
    if any(normalized.startswith(p) for p in _BLOCKED_PREFIXES):
        raise Http404()
    return serve(request, path, document_root=settings.MEDIA_ROOT)
