import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch, Count
from .models import Cours, Chapitre, Document
from .forms import CoursForm, ChapitreForm, DocumentForm


def liste_cours(request):
    """Affiche la liste de tous les cours actifs."""
    cours_list = Cours.objects.filter(actif=True).order_by('-date_creation')
    
    context = {
        'cours_list': cours_list,
        'titre_page': 'Tous les cours'
    }
    
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'apprentissage/partials/liste_cours.html', context)
    
    return render(request, 'apprentissage/liste_cours.html', context)


def detail_cours(request, cours_id):
    """Affiche un cours avec ses chapitres et documents groupés par type."""
    cours = get_object_or_404(Cours, id=cours_id, actif=True)
    
    # Précharger les chapitres avec les documents
    chapitres = cours.chapitres.filter(actif=True).prefetch_related(
        Prefetch(
            'documents',
            Document.objects.filter(actif=True).order_by('type_document', 'ordre')
        )
    ).order_by('ordre')
    
    # Grouper les documents par type dans chaque chapitre
    chapitres_data = []
    for chapitre in chapitres:
        # Grouper les documents par type et filtrer les vides
        documents_par_type = {}
        for doc in chapitre.documents.all():
            if settings.DEBUG:
                file_exists = False
                file_path = ''
                try:
                    file_path = doc.fichier_pdf.path
                    file_exists = os.path.exists(file_path)
                except Exception as exc:
                    file_path = f'INDISPONIBLE ({exc})'

                print(
                    f"[DEBUG PDF] doc_id={doc.id} titre='{doc.titre}' path='{file_path}' exists={file_exists}"
                )

            type_key = doc.get_type_document_display()
            if type_key not in documents_par_type:
                documents_par_type[type_key] = []
            documents_par_type[type_key].append(doc)
        
        # Créer la structure du chapitre avec les types regroupés et non-vides
        chapitre_data = {
            'chapitre': chapitre,
            'documents_par_type': documents_par_type
        }
        chapitres_data.append(chapitre_data)
    
    context = {
        'cours': cours,
        'chapitres_data': chapitres_data,
    }
    
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'apprentissage/partials/detail_cours.html', context)
    
    return render(request, 'apprentissage/detail_cours.html', context)


def detail_chapitre(request, cours_id, chapitre_id):
    """Affiche un chapitre avec ses documents regroupés par type."""
    cours = get_object_or_404(Cours, id=cours_id, actif=True)
    chapitre = get_object_or_404(
        Chapitre,
        id=chapitre_id,
        cours=cours,
        actif=True
    )
    
    # Regrouper les documents par type
    documents = chapitre.documents.filter(actif=True).order_by('type_document', 'ordre')
    documents_par_type = {}
    
    for doc in documents:
        type_key = doc.get_type_document_display()
        if type_key not in documents_par_type:
            documents_par_type[type_key] = []
        documents_par_type[type_key].append(doc)
    
    context = {
        'cours': cours,
        'chapitre': chapitre,
        'documents_par_type': documents_par_type,
    }
    
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'apprentissage/partials/detail_chapitre.html', context)
    
    return render(request, 'apprentissage/detail_chapitre.html', context)


def telecharger_document(request, document_id):
    """Télécharge le fichier PDF d'un document."""
    document = get_object_or_404(Document, id=document_id, actif=True)
    
    if not document.fichier_pdf:
        return HttpResponse('Fichier non disponible', status=404)
    
    response = HttpResponse(
        document.fichier_pdf.read(),
        content_type='application/pdf'
    )
    response['Content-Disposition'] = f'attachment; filename="{document.titre}.pdf"'
    return response
