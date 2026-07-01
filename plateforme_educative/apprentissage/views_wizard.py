import os
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apprentissage.models import Cours, Chapitre, Document, Niveau
from apprentissage.tasks import indexer_document_task

@login_required
def wizard_start(request):
    """Affiche le layout du wizard avec l'étape 1 par défaut."""
    # S'assurer que l'utilisateur est formateur ou admin
    if not (getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') in ['ADMIN', 'FORMATEUR'] or getattr(request.user, 'is_formateur', False)):
        raise PermissionDenied("Vous n'êtes pas autorisé à créer des cours.")
        
    niveaux = Niveau.objects.all()
    return render(request, 'apprentissage/wizard/wizard_layout.html', {'niveaux': niveaux})

@login_required
@require_http_methods(['POST'])
def wizard_step1_cours(request):
    """Étape 1 : Créer le cours avec Titre, Description et Niveau."""
    if not (getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') in ['ADMIN', 'FORMATEUR'] or getattr(request.user, 'is_formateur', False)):
        return HttpResponseBadRequest("Non autorisé")

    titre = request.POST.get('titre')
    description = request.POST.get('description')
    resume = request.POST.get('resume', '')
    niveau_id = request.POST.get('niveau')

    if not titre or not niveau_id:
        return HttpResponseBadRequest("Titre et Niveau sont obligatoires.")

    niveau = get_object_or_404(Niveau, pk=niveau_id)
    cours = Cours.objects.create(
        titre=titre,
        description=description,
        resume=resume,
        niveau=niveau,
        createur=request.user
    )

    return render(request, 'apprentissage/wizard/step2_image.html', {'cours': cours})

@login_required
@require_http_methods(['POST'])
def wizard_step2_image(request):
    """Étape 2 : Upload de l'image de couverture."""
    cours_id = request.POST.get('cours_id')
    cours = get_object_or_404(Cours, pk=cours_id, createur=request.user)

    couverture = request.FILES.get('couverture')
    if couverture:
        cours.image_couverture = couverture
        cours.save()

    # Qu'il y ait une image ou non, on passe à l'étape suivante.
    return render(request, 'apprentissage/wizard/step3_chapitre.html', {'cours': cours})

@login_required
@require_http_methods(['POST'])
def wizard_step3_chapitre(request):
    """Étape 3 : Créer le premier chapitre."""
    cours_id = request.POST.get('cours_id')
    cours = get_object_or_404(Cours, pk=cours_id, createur=request.user)

    titre = request.POST.get('titre')
    description = request.POST.get('description', '')

    if not titre:
        return HttpResponseBadRequest("Le titre du chapitre est obligatoire.")

    chapitre = Chapitre.objects.create(
        cours=cours,
        titre=titre,
        description=description,
        ordre=1
    )

    return render(request, 'apprentissage/wizard/step4_pdfs.html', {'chapitre': chapitre, 'cours': cours})

@login_required
@require_http_methods(['POST'])
def wizard_step4_pdfs(request):
    """Étape 4 : Upload des PDFs et indexation RAG."""
    chapitre_id = request.POST.get('chapitre_id')
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id, cours__createur=request.user)
    cours = chapitre.cours

    fichiers = request.FILES.getlist('documents')
    
    docs_ajoutes = 0
    for fichier in fichiers:
        if fichier.name.lower().endswith('.pdf'):
            doc = Document.objects.create(
                chapitre=chapitre,
                titre=fichier.name,
                fichier_pdf=fichier,
                type_document='COURS'
            )
            # Lancer l'indexation de manière synchrone
            try:
                indexer_document_task(str(doc.id), doc.fichier_pdf.path)
                docs_ajoutes += 1
            except Exception as e:
                # Fallback in case error occurs
                print(f"Erreur lancement tâche synchrone: {e}")

    return render(request, 'apprentissage/wizard/success.html', {'cours': cours, 'docs_ajoutes': docs_ajoutes})
