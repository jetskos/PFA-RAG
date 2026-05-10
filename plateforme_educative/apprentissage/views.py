import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import Q, Prefetch, Count
from .models import Cours, Chapitre, Document
from .forms import CoursForm, ChapitreForm, DocumentForm


@login_required
def espace_formateur(request):
    """Espace dédié aux formateurs pour gérer leurs cours."""
    # Si le champ createur est null pour certains cours, on filtre proprement
    mes_cours = Cours.objects.filter(createur=request.user).order_by('-date_creation')

    context = {
        'mes_cours': mes_cours,
    }

    return render(request, 'apprentissage/espace_formateur.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def nouveau_cours(request):
    """Créer un nouveau cours pour le formateur connecté."""
    if request.method == 'POST':
        form = CoursForm(request.POST)
        if form.is_valid():
            cours = form.save(commit=False)
            cours.createur = request.user
            cours.save()
            return redirect('apprentissage:espace_formateur')
    else:
        form = CoursForm()

    return render(request, 'apprentissage/cours_form.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def editer_cours(request, pk):
    """Modifier un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=pk)

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à modifier ce cours.")

    if request.method == 'POST':
        form = CoursForm(request.POST, instance=cours)
        if form.is_valid():
            form.save()
            return redirect('apprentissage:espace_formateur')
    else:
        form = CoursForm(instance=cours)

    return render(request, 'apprentissage/cours_form.html', {'form': form})


@login_required
@require_http_methods(['POST'])
def supprimer_cours(request, pk):
    """Supprimer un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=pk)

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à supprimer ce cours.")

    cours.delete()
    return redirect('apprentissage:espace_formateur')


@login_required
def gerer_cours(request, pk):
    """Page de gestion d'un cours, accessible uniquement à son formateur propriétaire."""
    cours = get_object_or_404(Cours, pk=pk)

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à modifier ce cours.")

    chapitres = cours.chapitres.all().order_by('ordre')

    context = {
        'cours': cours,
        'chapitres': chapitres,
    }

    return render(request, 'apprentissage/gerer_cours.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def ajouter_chapitre(request, cours_id):
    """Ajouter un chapitre via HTMX pour un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=cours_id)

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à modifier ce cours.")

    if request.method == 'POST':
        form = ChapitreForm(request.POST)
        if form.is_valid():
            chapitre = form.save(commit=False)
            chapitre.cours = cours
            chapitre.save()
            chapitres = cours.chapitres.all().order_by('ordre')
            return render(request, 'apprentissage/partials/chapitres_list.html', {
                'cours': cours,
                'chapitres': chapitres,
            })
    else:
        form = ChapitreForm()

    return render(request, 'apprentissage/partials/chapitre_form.html', {
        'form': form,
        'cours': cours,
        'action_url': reverse('apprentissage:ajouter_chapitre', args=[cours.pk]),
        'submit_label': 'Soumettre',
    })


@login_required
def gerer_chapitre(request, chapitre_id):
    """Affiche un chapitre et ses documents. Accessible au formateur propriétaire du cours."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à accéder à ce contenu.")

    documents = chapitre.documents.all().order_by('type_document', 'ordre')

    context = {
        'chapitre': chapitre,
        'documents': documents,
        'cours': cours,
    }

    return render(request, 'apprentissage/partials/chapitre_detail.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def editer_chapitre(request, chapitre_id):
    """Modifier un chapitre appartenant au formateur connecté."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à modifier ce chapitre.")

    if request.method == 'POST':
        form = ChapitreForm(request.POST, instance=chapitre)
        if form.is_valid():
            form.save()
            chapitres = cours.chapitres.all().order_by('ordre')
            return render(request, 'apprentissage/partials/chapitres_list.html', {
                'cours': cours,
                'chapitres': chapitres,
            })
    else:
        form = ChapitreForm(instance=chapitre)

    return render(request, 'apprentissage/partials/chapitre_form.html', {
        'form': form,
        'cours': cours,
        'action_url': reverse('apprentissage:editer_chapitre', args=[chapitre.pk]),
        'submit_label': 'Enregistrer',
    })


@login_required
@require_http_methods(['POST'])
def supprimer_chapitre(request, chapitre_id):
    """Supprimer un chapitre appartenant au formateur connecté."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à supprimer ce chapitre.")

    chapitre.delete()
    chapitres = cours.chapitres.all().order_by('ordre')
    return render(request, 'apprentissage/partials/chapitres_list.html', {
        'cours': cours,
        'chapitres': chapitres,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def ajouter_document(request, chapitre_id):
    """Ajouter un document (PDF) à un chapitre via HTMX. Gère multipart/form-data."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à ajouter un document.")

    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.chapitre = chapitre
            document.save()
            # Retourner la liste des documents mise à jour
            documents = chapitre.documents.all().order_by('type_document', 'ordre')
            return render(request, 'apprentissage/partials/documents_list.html', {
                'documents': documents,
                'chapitre': chapitre,
            })
    else:
        form = DocumentForm()

    return render(request, 'apprentissage/partials/document_form.html', {
        'form': form,
        'chapitre': chapitre,
        'action_url': reverse('apprentissage:ajouter_document', args=[chapitre.pk]),
        'submit_label': 'Soumettre',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def editer_document(request, document_id):
    """Modifier un document appartenant au formateur connecté."""
    document = get_object_or_404(Document, pk=document_id)
    chapitre = document.chapitre
    cours = chapitre.cours

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à modifier ce document.")

    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            documents = chapitre.documents.all().order_by('type_document', 'ordre')
            return render(request, 'apprentissage/partials/documents_list.html', {
                'documents': documents,
                'chapitre': chapitre,
            })
    else:
        form = DocumentForm(instance=document)

    return render(request, 'apprentissage/partials/document_form.html', {
        'form': form,
        'chapitre': chapitre,
        'document': document,
        'action_url': reverse('apprentissage:editer_document', args=[document.pk]),
        'submit_label': 'Enregistrer',
    })


@login_required
@require_http_methods(['POST'])
def supprimer_document(request, document_id):
    """Supprimer un document appartenant au formateur connecté."""
    document = get_object_or_404(Document, pk=document_id)
    chapitre = document.chapitre
    cours = chapitre.cours

    if not request.user.is_formateur or cours.createur != request.user:
        return HttpResponseForbidden("Vous n'êtes pas autorisé à supprimer ce document.")

    document.delete()
    documents = chapitre.documents.all().order_by('type_document', 'ordre')
    return render(request, 'apprentissage/partials/documents_list.html', {
        'documents': documents,
        'chapitre': chapitre,
    })


@login_required
def liste_cours(request):
    """Affiche la liste de tous les cours actifs."""
    # Superusers and formateurs voient tout
    if request.user.is_superuser or request.user.is_formateur:
        cours_list = Cours.objects.filter(actif=True).order_by('-date_creation')
    else:
        # Étudiants voient uniquement les cours correspondant à leur niveau
        user_niveau = getattr(request.user, 'niveau', None)
        if user_niveau:
            cours_list = Cours.objects.filter(actif=True, niveau__iexact=user_niveau).order_by('-date_creation')
        else:
            cours_list = Cours.objects.filter(actif=True).order_by('-date_creation')
    
    context = {
        'cours_list': cours_list,
        'titre_page': 'Tous les cours'
    }
    
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'apprentissage/partials/liste_cours.html', context)
    
    return render(request, 'apprentissage/liste_cours.html', context)


@login_required
def detail_cours(request, cours_id):
    """Affiche un cours avec ses chapitres et documents groupés par type."""
    cours = get_object_or_404(Cours, id=cours_id, actif=True)

    # Sécurité : empêcher un étudiant d'accéder à un cours hors de son niveau
    if request.user.is_authenticated and not (request.user.is_superuser or request.user.is_formateur):
        user_niveau = getattr(request.user, 'niveau', '').lower()
        cours_niveau = getattr(cours, 'niveau', '').lower()
        if user_niveau and cours_niveau and user_niveau != cours_niveau:
            return HttpResponseForbidden("Ce cours ne correspond pas à votre niveau actuel.")
    
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


@login_required
@require_http_methods(['POST'])
def valider_chapitre(request, chapitre_id):
    """Marque un chapitre comme validé pour l'étudiant connecté."""
    from .models import Progression
    
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id, actif=True)
    
    # Récupère ou crée la progression pour cet étudiant et ce cours
    progression, created = Progression.objects.get_or_create(
        etudiant=request.user,
        cours=chapitre.cours
    )
    
    # Ajoute le chapitre aux chapitres validés
    progression.chapitres_valides.add(chapitre)
    
    # Retourne un fragment HTML simple
    return HttpResponse(
        '<button class="btn" disabled style="background:#4caf50; color:#fff;">✓ Chapitre terminé</button>'
    )
