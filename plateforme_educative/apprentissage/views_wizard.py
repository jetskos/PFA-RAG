import logging

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from apprentissage.models import Cours, Chapitre, Document, Niveau
from apprentissage.tasks import indexer_document_task

logger = logging.getLogger(__name__)


def _peut_creer_cours(user):
    return bool(
        user.is_superuser
        or getattr(user, 'role', '') in ('ADMIN', 'FORMATEUR')
        or getattr(user, 'is_formateur', False)
    )


def _exiger_formateur(user):
    if not _peut_creer_cours(user):
        raise PermissionDenied(_("Vous n'êtes pas autorisé à créer des cours."))


@login_required
def wizard_start(request):
    """Affiche le layout du wizard avec l'étape 1 par défaut."""
    _exiger_formateur(request.user)
    niveaux = Niveau.objects.all()
    return render(request, 'apprentissage/wizard/wizard_layout.html', {'niveaux': niveaux})


@login_required
@require_http_methods(['POST'])
def wizard_step1_cours(request):
    """Étape 1 : créer le cours (Titre, Description, Niveau) — en BROUILLON."""
    _exiger_formateur(request.user)

    titre = (request.POST.get('titre') or '').strip()
    description = request.POST.get('description', '')
    resume = request.POST.get('resume', '')
    niveau_id = request.POST.get('niveau')

    if not titre or not niveau_id:
        return HttpResponseBadRequest(_("Titre et Niveau sont obligatoires."))

    niveau = get_object_or_404(Niveau, pk=niveau_id)
    # actif=False : le cours reste invisible au catalogue tant que le wizard
    # n'est pas terminé (évite les cours vides publiés si l'onglet est fermé).
    cours = Cours.objects.create(
        titre=titre,
        description=description,
        resume=resume,
        niveau=niveau,
        createur=request.user,
        actif=False,
    )

    return render(request, 'apprentissage/wizard/step2_image.html', {'cours': cours})


@login_required
@require_http_methods(['POST'])
def wizard_step2_image(request):
    """Étape 2 : upload de l'image de couverture."""
    _exiger_formateur(request.user)
    cours = get_object_or_404(Cours, pk=request.POST.get('cours_id'), createur=request.user)

    couverture = request.FILES.get('couverture')
    if couverture:
        if not couverture.content_type.startswith('image/'):
            return HttpResponseBadRequest(_("Le fichier de couverture doit être une image."))
        cours.image_couverture = couverture
        cours.save()

    return render(request, 'apprentissage/wizard/step3_chapitre.html', {'cours': cours})


@login_required
@require_http_methods(['POST'])
def wizard_step3_chapitre(request):
    """Étape 3 : créer le premier chapitre."""
    _exiger_formateur(request.user)
    cours = get_object_or_404(Cours, pk=request.POST.get('cours_id'), createur=request.user)

    titre = (request.POST.get('titre') or '').strip()
    description = request.POST.get('description', '')

    if not titre:
        return HttpResponseBadRequest(_("Le titre du chapitre est obligatoire."))

    chapitre = Chapitre.objects.create(
        cours=cours,
        titre=titre,
        description=description,
        ordre=1,
    )

    return render(request, 'apprentissage/wizard/step4_pdfs.html', {'chapitre': chapitre, 'cours': cours})


@login_required
@require_http_methods(['POST'])
def wizard_step4_pdfs(request):
    """Étape 4 : upload des PDF, indexation RAG, puis PUBLICATION du cours."""
    _exiger_formateur(request.user)
    chapitre = get_object_or_404(
        Chapitre, pk=request.POST.get('chapitre_id'), cours__createur=request.user,
    )
    cours = chapitre.cours

    from apprentissage.models import validate_file_size

    docs_ajoutes = 0
    for fichier in request.FILES.getlist('documents'):
        if not fichier.name.lower().endswith('.pdf'):
            continue
        try:
            validate_file_size(fichier)  # même plafond que le modèle Document
        except ValidationError as exc:
            logger.warning("Wizard : PDF « %s » rejeté (%s)", fichier.name, exc.messages)
            continue
        doc = Document.objects.create(
            chapitre=chapitre,
            titre=fichier.name,
            fichier_pdf=fichier,
            type_document='COURS',
        )
        try:
            indexer_document_task(str(doc.id), doc.fichier_pdf.path)
        except Exception:
            logger.exception("Wizard : indexation RAG du document %s échouée", doc.id)
        docs_ajoutes += 1

    # Le cours a maintenant au moins un chapitre : on le publie.
    if not cours.actif:
        cours.actif = True
        cours.save(update_fields=['actif'])
        try:
            from apprentissage.views import _notifier_nouveau_cours
            _notifier_nouveau_cours(cours)
        except Exception:
            logger.exception("Wizard : notification « nouveau cours » échouée")

    return render(request, 'apprentissage/wizard/success.html', {'cours': cours, 'docs_ajoutes': docs_ajoutes})
