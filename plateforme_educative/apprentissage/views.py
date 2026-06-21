from django.db import transaction
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import Q, Prefetch, Count
from .models import Cours, Chapitre, Document, Progression, ChapitreVisite, ChapitreComplete, Devoir, Soumission, Evenement
from django.contrib import messages
from .forms import CoursForm, ChapitreForm, DocumentForm
from apprentissage.mixins import (
    FormateurCoursRequiredMixin,
    FormateurChapitreRequiredMixin,
    FormateurDevoirRequiredMixin,
    ElevePropreDonneeMixin
)



def _htmx_modal_error_response(request, template_name, context):
    """Render a form back into the modal when an HTMX submission is invalid."""
    response = render(request, template_name, context, status=400)
    if request.headers.get('HX-Request') == 'true':
        response['HX-Retarget'] = '#modal-body'
    return response


@login_required
def espace_formateur(request):
    """Espace dédié aux formateurs pour gérer leurs cours."""
    # Si le champ createur est null pour certains cours, on filtre proprement
    mes_cours = Cours.objects.filter(createur=request.user).order_by('-date_creation')

    # Récupérer les devoirs créés par le formateur avec le nombre de soumissions
    from django.db.models import Count, Q
    devoirs = Devoir.objects.filter(createur=request.user).select_related('chapitre', 'chapitre__cours').annotate(
        total_soumissions=Count('soumissions'),
        soumissions_a_noter=Count('soumissions', filter=Q(soumissions__note__isnull=True))
    ).order_by('-date_creation')

    context = {
        'mes_cours': mes_cours,
        'devoirs': devoirs,
    }

    return render(request, 'apprentissage/espace_formateur.html', context)



@login_required
@require_http_methods(['GET', 'POST'])
def nouveau_cours(request):
    """Créer un nouveau cours pour le formateur connecté. Réservé aux FORMATEURS."""
    if not (request.user.is_formateur or request.user.is_superuser):
        return HttpResponseForbidden("Accès réservé aux formateurs.")
    if request.method == 'POST':
        form = CoursForm(request.POST, request.FILES)
        if form.is_valid():
            cours = form.save(commit=False)
            cours.createur = request.user
            cours.save()
            try:
                from accounts.models import Utilisateur
                from accounts.notifications import notifier
                eleves = Utilisateur.objects.filter(
                    role='ELEVE',
                    is_active=True,
                    classe__niveau=cours.niveau
                )
                for eleve in eleves:
                    notifier(
                        destinataire=eleve,
                        type='NOUVEAU_COURS',
                        titre=f"Nouveau cours : {cours.titre}",
                        message=f"Le cours '{cours.titre}' est disponible pour votre niveau {cours.niveau.nom}.",
                        url=reverse('apprentissage:detail_cours', args=[cours.id])
                    )
            except Exception as e:
                pass
            return redirect('apprentissage:espace_formateur')
    else:
        form = CoursForm()

    return render(request, 'apprentissage/cours_form.html', {'form': form})


@login_required
@FormateurCoursRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def editer_cours(request, pk):
    """Modifier un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=pk)

    if request.method == 'POST':
        form = CoursForm(request.POST, request.FILES, instance=cours)
        if form.is_valid():
            form.save()
            return redirect('apprentissage:espace_formateur')
    else:
        form = CoursForm(instance=cours)

    return render(request, 'apprentissage/cours_form.html', {'form': form})


@login_required
@FormateurCoursRequiredMixin.as_decorator()
@require_http_methods(['POST'])
def supprimer_cours(request, pk):
    """Supprimer un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=pk)

    cours.delete()
    return redirect('apprentissage:espace_formateur')


@login_required
@FormateurCoursRequiredMixin.as_decorator()
def gerer_cours(request, pk):
    """Page de gestion d'un cours, accessible uniquement à son formateur propriétaire."""
    cours = get_object_or_404(Cours, pk=pk)

    chapitres = cours.chapitres.all().order_by('ordre')

    context = {
        'cours': cours,
        'chapitres': chapitres,
        'can_edit_documents': True,
    }

    return render(request, 'apprentissage/gerer_cours.html', context)


@login_required
@FormateurCoursRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def ajouter_chapitre(request, cours_id):
    """Ajouter un chapitre via HTMX pour un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=cours_id)

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

    context = {
        'form': form,
        'cours': cours,
        'action_url': reverse('apprentissage:ajouter_chapitre', args=[cours.pk]),
        'submit_label': 'Soumettre',
    }

    if request.method == 'POST':
        return _htmx_modal_error_response(request, 'apprentissage/partials/chapitre_form.html', context)

    return render(request, 'apprentissage/partials/chapitre_form.html', context)


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
def gerer_chapitre(request, chapitre_id):
    """Affiche un chapitre et ses documents. Accessible au formateur propriétaire du cours."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    documents = chapitre.documents.all().order_by('type_document', 'ordre')

    context = {
        'chapitre': chapitre,
        'documents': documents,
        'cours': cours,
        'can_edit_documents': True,
    }

    return render(request, 'apprentissage/partials/chapitre_detail.html', context)


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def editer_chapitre(request, chapitre_id):
    """Modifier un chapitre appartenant au formateur connecté."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

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

    context = {
        'form': form,
        'cours': cours,
        'action_url': reverse('apprentissage:editer_chapitre', args=[chapitre.pk]),
        'submit_label': 'Enregistrer',
    }

    if request.method == 'POST':
        return _htmx_modal_error_response(request, 'apprentissage/partials/chapitre_form.html', context)

    return render(request, 'apprentissage/partials/chapitre_form.html', context)


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['POST'])
def supprimer_chapitre(request, chapitre_id):
    """Supprimer un chapitre appartenant au formateur connecté."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    chapitre.delete()
    chapitres = cours.chapitres.all().order_by('ordre')
    return render(request, 'apprentissage/partials/chapitres_list.html', {
        'cours': cours,
        'chapitres': chapitres,
    })


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def ajouter_document(request, chapitre_id):
    """Ajouter un document (PDF) à un chapitre via HTMX. Gère multipart/form-data."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

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
                'can_edit_documents': True,
            })
    else:
        form = DocumentForm()

    context = {
        'form': form,
        'chapitre': chapitre,
        'action_url': reverse('apprentissage:ajouter_document', args=[chapitre.pk]),
        'submit_label': 'Soumettre',
    }

    if request.method == 'POST':
        return _htmx_modal_error_response(request, 'apprentissage/partials/document_form.html', context)

    return render(request, 'apprentissage/partials/document_form.html', context)


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def editer_document(request, document_id):
    """Modifier un document appartenant au formateur connecté."""
    document = get_object_or_404(Document, pk=document_id)
    chapitre = document.chapitre
    cours = chapitre.cours

    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            documents = chapitre.documents.all().order_by('type_document', 'ordre')
            return render(request, 'apprentissage/partials/documents_list.html', {
                'documents': documents,
                'chapitre': chapitre,
                'can_edit_documents': True,
            })
    else:
        form = DocumentForm(instance=document)

    context = {
        'form': form,
        'chapitre': chapitre,
        'document': document,
        'action_url': reverse('apprentissage:editer_document', args=[document.pk]),
        'submit_label': 'Enregistrer',
    }

    if request.method == 'POST':
        return _htmx_modal_error_response(request, 'apprentissage/partials/document_form.html', context)

    return render(request, 'apprentissage/partials/document_form.html', context)


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['POST'])
def supprimer_document(request, document_id):
    """Supprimer un document appartenant au formateur connecté."""
    document = get_object_or_404(Document, pk=document_id)
    chapitre = document.chapitre
    cours = chapitre.cours

    document.delete()
    documents = chapitre.documents.all().order_by('type_document', 'ordre')
    return render(request, 'apprentissage/partials/documents_list.html', {
        'documents': documents,
        'chapitre': chapitre,
        'can_edit_documents': True,
    })


@login_required
def liste_cours(request):
    """Affiche la liste de tous les cours actifs (et brouillons pour les créateurs)."""
    q = request.GET.get('q', '').strip()
    
    if request.user.is_superuser:
        cours_list = Cours.objects.select_related('createur', 'niveau').all()
    elif request.user.is_formateur:
        # Formateurs : Leurs propres cours (publiés ou non) + Les autres cours publiés
        cours_list = Cours.objects.select_related('createur', 'niveau').filter(
            Q(createur=request.user) | Q(actif=True)
        )
    else:
        # Étudiants voient uniquement les cours actifs correspondant à leur niveau
        classe = getattr(request.user, 'classe', None)
        niveau = getattr(classe, 'niveau', None)
        if niveau:
            cours_list = Cours.objects.select_related('createur', 'niveau').filter(actif=True, niveau=niveau)
        else:
            cours_list = Cours.objects.select_related('createur', 'niveau').filter(actif=True)
            
    # Application de la recherche si présente
    if q:
        cours_list = cours_list.filter(
            Q(titre__icontains=q) | 
            Q(createur__email__icontains=q) |
            Q(createur__first_name__icontains=q) |
            Q(createur__last_name__icontains=q)
        )
        
    cours_list = cours_list.order_by('-date_creation').distinct()
    
    context = {
        'cours_list': cours_list,
        'titre_page': 'Catalogue des cours',
        'q': q
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
        classe = getattr(request.user, 'classe', None)
        user_niveau = getattr(classe, 'niveau', None)
        if user_niveau and cours.niveau_id != user_niveau.id:
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
    
    # Calcul des infos RAG et vidéo pour le premier chapitre
    chapitre_initial = None
    session_assistant = None
    is_direct_video = False
    is_youtube = False
    is_vimeo = False
    vimeo_embed_url = ""
    chapitre_precedent = None
    chapitre_suivant = None

    if chapitres.exists():
        chapitre_initial = chapitres.first()
        chapitre_precedent = None
        chapitre_suivant = chapitres.filter(ordre__gt=chapitre_initial.ordre).order_by('ordre').first()

        url = chapitre_initial.url_video or ''
        url_lower = url.lower()
        is_direct_video = any(url_lower.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov'])
        is_youtube = 'youtube.com' in url_lower or 'youtu.be' in url_lower
        is_vimeo = 'vimeo.com' in url_lower

        if is_vimeo:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(url)
                parts = parsed.path.strip('/').split('/')
                video_id = ''
                for part in reversed(parts):
                    if part.isdigit():
                        video_id = part
                        break
                if video_id:
                    vimeo_embed_url = f"https://player.vimeo.com/video/{video_id}"
                else:
                    vimeo_embed_url = url
            except Exception:
                vimeo_embed_url = url

        if request.user.is_authenticated:
            from tuteur_ia.models import SessionAssistant
            session_assistant, _ = SessionAssistant.objects.get_or_create(
                etudiant=request.user,
                chapitre=chapitre_initial
            )
            
    context = {
        'cours': cours,
        'chapitres_data': chapitres_data,
        'can_edit_documents': False,
        'chapitre_initial_assistant': session_assistant,
        'chapitre_initial_is_direct_video': is_direct_video,
        'chapitre_initial_is_youtube': is_youtube,
        'chapitre_initial_is_vimeo': is_vimeo,
        'chapitre_initial_vimeo_embed_url': vimeo_embed_url,
        'chapitre_initial_precedent': chapitre_precedent,
        'chapitre_initial_suivant': chapitre_suivant,
    }
    
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'apprentissage/partials/detail_cours.html', context)
    
    return render(request, 'apprentissage/detail_cours.html', context)


@login_required
def detail_chapitre(request, cours_id, chapitre_id):
    """Affiche un chapitre avec ses documents regroupés par type."""
    cours = get_object_or_404(Cours, id=cours_id, actif=True)
    chapitre = get_object_or_404(
        Chapitre,
        id=chapitre_id,
        cours=cours,
        actif=True
    )

    if request.user.is_authenticated:
        ChapitreVisite.objects.update_or_create(
            etudiant=request.user,
            chapitre=chapitre,
        )
    
    # Regrouper les documents par type
    documents = chapitre.documents.filter(actif=True).order_by('type_document', 'ordre')
    documents_par_type = {}
    
    for doc in documents:
        type_key = doc.get_type_document_display()
        if type_key not in documents_par_type:
            documents_par_type[type_key] = []
        documents_par_type[type_key].append(doc)
        
    # Navigation : chapitre précédent et suivant
    chapitres_cours = Chapitre.objects.filter(cours=cours, actif=True)
    chapitre_precedent = chapitres_cours.filter(ordre__lt=chapitre.ordre).order_by('-ordre').first()
    chapitre_suivant = chapitres_cours.filter(ordre__gt=chapitre.ordre).order_by('ordre').first()
    
    # Analyse de la vidéo
    url = chapitre.url_video or ''
    url_lower = url.lower()
    is_direct_video = any(url_lower.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov'])
    is_youtube = 'youtube.com' in url_lower or 'youtu.be' in url_lower
    is_vimeo = 'vimeo.com' in url_lower
    
    vimeo_embed_url = ''
    if is_vimeo:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            parts = parsed.path.strip('/').split('/')
            video_id = ''
            for part in reversed(parts):
                if part.isdigit():
                    video_id = part
                    break
            if video_id:
                vimeo_embed_url = f"https://player.vimeo.com/video/{video_id}"
            else:
                vimeo_embed_url = url
        except Exception:
            vimeo_embed_url = url

    # Charger/Créer la session RAG Assistant
    session_assistant = None
    if request.user.is_authenticated:
        from tuteur_ia.models import SessionAssistant
        session_assistant, _ = SessionAssistant.objects.get_or_create(
            etudiant=request.user,
            chapitre=chapitre
        )
    
    context = {
        'cours': cours,
        'chapitre': chapitre,
        'documents_par_type': documents_par_type,
        'can_edit_documents': False,
        'chapitre_precedent': chapitre_precedent,
        'chapitre_suivant': chapitre_suivant,
        'is_direct_video': is_direct_video,
        'is_youtube': is_youtube,
        'is_vimeo': is_vimeo,
        'vimeo_embed_url': vimeo_embed_url,
        'session_assistant': session_assistant,
    }
    
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'apprentissage/partials/detail_chapitre.html', context)
    
    return render(request, 'apprentissage/detail_chapitre.html', context)



@login_required
def telecharger_document(request, document_id):
    """Télécharge le fichier PDF d'un document. Réservé aux utilisateurs connectés."""
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
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id, actif=True)
    
    # Récupère ou crée la progression pour cet étudiant et ce cours
    progression, created = Progression.objects.get_or_create(
        etudiant=request.user,
        cours=chapitre.cours
    )
    
    # Ajoute le chapitre aux chapitres validés
    progression.chapitres_valides.add(chapitre)
    ChapitreComplete.objects.update_or_create(
        etudiant=request.user,
        chapitre=chapitre,
    )
    
    # Retourne un fragment HTML simple
    return HttpResponse(
        '<button class="btn" disabled style="background:#4caf50; color:#fff;">✓ Chapitre terminé</button>'
    )


# ── Carnet de notes (Élève) ───────────────────────────────────────────────────

@login_required
def mes_notes_view(request):
    """Affiche le carnet de notes agrégé de l'étudiant connecté."""
    from .grades import calculer_bulletin
    bulletin = calculer_bulletin(request.user)
    return render(request, 'apprentissage/mes_notes.html', {
        'bulletin': bulletin,
        'titre_page': 'Mon carnet de notes',
    })


@login_required
def exporter_bulletin_csv(request):
    """Exporte le bulletin de notes de l'étudiant en CSV."""
    import csv
    from .grades import calculer_bulletin
    bulletin = calculer_bulletin(request.user)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="bulletin_notes.csv"'
    response.write('\ufeff')  # BOM pour Excel

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Cours', 'Chapitre', 'Ordre', 'Meilleur Score (/100)', 'Statut'])

    for cours_data in bulletin['cours']:
        for ch_data in cours_data['chapitres']:
            writer.writerow([
                cours_data['cours'].titre,
                ch_data['chapitre'].titre,
                ch_data['chapitre'].ordre,
                ch_data['meilleur_score'] if ch_data['meilleur_score'] is not None else 'Non tenté',
                ch_data['statut'],
            ])

    return response


# ── Carnet de notes (Formateur) ───────────────────────────────────────────────

@login_required
def formateur_notes_view(request):
    """Affiche les notes agrégées de tous les élèves de ses cours, avec filtre de classe."""
    if not (request.user.is_formateur or request.user.is_superuser):
        return HttpResponseForbidden("Accès réservé aux formateurs.")

    from .grades import calculer_bulletin
    from accounts.models import Utilisateur, Classe

    mes_cours = Cours.objects.filter(createur=request.user).prefetch_related('chapitres')
    cours_ids = set(str(c.id) for c in mes_cours)

    # Récupérer les classes associées aux niveaux de mes cours pour le filtre
    classes = Classe.objects.filter(niveau__in=mes_cours.values('niveau')).distinct()

    # Récupérer le filtre de classe
    classe_id = request.GET.get('classe')
    
    etudiants = Utilisateur.objects.filter(
        progressions__cours__in=mes_cours
    ).distinct()

    if classe_id:
        etudiants = etudiants.filter(classe_id=classe_id)

    etudiants = etudiants.order_by('email')

    # Calculer les notes par étudiant et collecter pour les moyennes globales de cours
    notes_etudiants = []
    scores_par_cours = {str(c.id): [] for c in mes_cours}

    for etudiant in etudiants:
        bulletin = calculer_bulletin(etudiant)
        cours_formateur = [
            c for c in bulletin['cours']
            if str(c['cours'].id) in cours_ids
        ]
        if cours_formateur:
            # Collecter les moyennes de cours pour la moyenne de classe
            for c_data in cours_formateur:
                if c_data['moyenne_cours'] is not None:
                    scores_par_cours[str(c_data['cours'].id)].append(c_data['moyenne_cours'])

            # Repérage des élèves en difficulté (moyenne générale < 50)
            en_difficulte = False
            if bulletin['moyenne_generale'] is not None and bulletin['moyenne_generale'] < 50:
                en_difficulte = True

            notes_etudiants.append({
                'etudiant': etudiant,
                'cours': cours_formateur,
                'moyenne_generale': bulletin['moyenne_generale'],
                'en_difficulte': en_difficulte,
            })

    # Calculer la moyenne de classe pour chaque cours
    moyenne_classe_par_cours = {}
    for c in mes_cours:
        scores = scores_par_cours[str(c.id)]
        moyenne_classe_par_cours[str(c.id)] = round(sum(scores) / len(scores), 1) if scores else None

    return render(request, 'apprentissage/formateur_notes.html', {
        'notes_etudiants': notes_etudiants,
        'mes_cours': mes_cours,
        'classes': classes,
        'classe_selectionnee': classe_id,
        'moyenne_classe_par_cours': moyenne_classe_par_cours,
        'titre_page': 'Notes de mes étudiants',
    })


@login_required
def exporter_notes_classe_csv(request):
    """Exporte les notes de tous les élèves des cours du formateur en CSV avec support du filtre de classe."""
    if not (request.user.is_formateur or request.user.is_superuser):
        return HttpResponseForbidden("Accès réservé aux formateurs.")

    import csv
    from .grades import calculer_bulletin
    from accounts.models import Utilisateur

    mes_cours = Cours.objects.filter(createur=request.user)
    cours_ids = set(str(c.id) for c in mes_cours)

    etudiants = Utilisateur.objects.filter(
        progressions__cours__in=mes_cours
    ).distinct()

    classe_id = request.GET.get('classe')
    if classe_id:
        etudiants = etudiants.filter(classe_id=classe_id)

    etudiants = etudiants.order_by('email')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="notes_classe.csv"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Étudiant', 'Classe', 'Cours', 'Chapitre', 'Ordre', 'Meilleur Score', 'Statut'])

    for etudiant in etudiants:
        bulletin = calculer_bulletin(etudiant)
        for cours_data in bulletin['cours']:
            if str(cours_data['cours'].id) not in cours_ids:
                continue
            for ch_data in cours_data['chapitres']:
                writer.writerow([
                    etudiant.email,
                    etudiant.classe.nom if etudiant.classe else 'Sans classe',
                    cours_data['cours'].titre,
                    ch_data['chapitre'].titre,
                    ch_data['chapitre'].ordre,
                    ch_data['meilleur_score'] if ch_data['meilleur_score'] is not None else 'Non tenté',
                    ch_data['statut'],
                ])

    return response



# ── Devoirs (Formateur) ───────────────────────────────────────────────────────

@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def devoir_creer_view(request, chapitre_id):
    """Crée un devoir pour un chapitre appartenant au formateur."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    from .forms import DevoirForm
    if request.method == 'POST':
        form = DevoirForm(request.POST, request.FILES)
        if form.is_valid():
            devoir = form.save(commit=False)
            devoir.chapitre = chapitre
            devoir.createur = request.user
            devoir.save()

            # Notifier les élèves du niveau concerné
            try:
                from accounts.models import Utilisateur
                from accounts.notifications import notifier
                eleves = Utilisateur.objects.filter(
                    role='ELEVE',
                    is_active=True,
                    classe__niveau=cours.niveau
                )
                for eleve in eleves:
                    notifier(
                        destinataire=eleve,
                        type='NOUVEAU_COURS',
                        titre=f"Nouveau devoir : {devoir.titre}",
                        message=f"Un nouveau devoir '{devoir.titre}' a été publié dans le chapitre '{chapitre.titre}'.",
                        url=reverse('apprentissage:devoir_detail', args=[devoir.pk])
                    )
            except Exception:
                pass

            return redirect('apprentissage:gerer_chapitre', chapitre_id=chapitre.pk)
    else:
        form = DevoirForm()

    return render(request, 'apprentissage/devoir_form.html', {
        'form': form,
        'chapitre': chapitre,
        'cours': cours,
        'action': 'Créer',
    })


@login_required
@FormateurDevoirRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def devoir_editer_view(request, devoir_id):
    """Modifie un devoir appartenant au formateur."""
    devoir = get_object_or_404(Devoir, pk=devoir_id)
    cours = devoir.chapitre.cours

    from .forms import DevoirForm
    if request.method == 'POST':
        form = DevoirForm(request.POST, request.FILES, instance=devoir)
        if form.is_valid():
            form.save()
            return redirect('apprentissage:gerer_chapitre', chapitre_id=devoir.chapitre.pk)
    else:
        form = DevoirForm(instance=devoir)

    return render(request, 'apprentissage/devoir_form.html', {
        'form': form,
        'chapitre': devoir.chapitre,
        'cours': cours,
        'devoir': devoir,
        'action': 'Modifier',
    })


@login_required
@FormateurDevoirRequiredMixin.as_decorator()
@require_http_methods(['POST'])
def devoir_supprimer_view(request, devoir_id):
    """Supprime un devoir appartenant au formateur."""
    devoir = get_object_or_404(Devoir, pk=devoir_id)
    cours = devoir.chapitre.cours

    chapitre_pk = devoir.chapitre.pk
    devoir.delete()
    return redirect('apprentissage:gerer_chapitre', chapitre_id=chapitre_pk)


@login_required
@FormateurDevoirRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def soumission_noter_view(request, soumission_id):
    """Permet au formateur de noter une soumission d'élève."""
    soumission = get_object_or_404(Soumission, pk=soumission_id)
    devoir = soumission.devoir
    cours = devoir.chapitre.cours

    from .forms import NotationSoumissionForm
    if request.method == 'POST':
        form = NotationSoumissionForm(request.POST, instance=soumission)
        if form.is_valid():
            from django.utils import timezone as tz
            s = form.save(commit=False)
            s.corrige_par = request.user
            s.date_correction = tz.now()
            s.save()

            # Notifier l'étudiant
            try:
                from accounts.notifications import notifier
                notifier(
                    destinataire=soumission.etudiant,
                    type='QCM_CORRIGE',
                    titre=f"Devoir corrigé : {devoir.titre}",
                    message=f"Votre devoir '{devoir.titre}' a été corrigé. Note : {s.note}/{devoir.note_max}.",
                    url=reverse('apprentissage:devoir_detail', args=[devoir.pk])
                )
            except Exception:
                pass

            return redirect('apprentissage:devoir_detail', devoir_id=devoir.pk)
    else:
        form = NotationSoumissionForm(instance=soumission)

    return render(request, 'apprentissage/soumission_eval.html', {
        'soumission': soumission,
        'devoir': devoir,
        'cours': cours,
        'form': form,
    })


# ── Devoirs (Élève) ───────────────────────────────────────────────────────────

@login_required
def devoirs_liste_view(request):
    """Liste tous les devoirs actifs disponibles pour l'étudiant connecté."""
    # Filtrer par niveau si l'étudiant a une classe
    classe = getattr(request.user, 'classe', None)
    niveau = getattr(classe, 'niveau', None)

    devoirs_qs = Devoir.objects.filter(actif=True).select_related(
        'chapitre', 'chapitre__cours', 'chapitre__cours__niveau'
    ).order_by('-date_creation')

    if niveau:
        devoirs_qs = devoirs_qs.filter(chapitre__cours__niveau=niveau)

    # Annoter avec la soumission de l'étudiant si elle existe
    soumissions_map = {
        str(s.devoir_id): s
        for s in Soumission.objects.filter(etudiant=request.user)
    }

    devoirs_data = []
    for devoir in devoirs_qs:
        devoirs_data.append({
            'devoir': devoir,
            'soumission': soumissions_map.get(str(devoir.id)),
        })

    return render(request, 'apprentissage/devoirs_liste.html', {
        'devoirs_data': devoirs_data,
        'titre_page': 'Mes devoirs',
    })


@login_required
def devoir_detail_view(request, devoir_id):
    """Affiche un devoir et le formulaire de soumission pour l'étudiant."""
    devoir = get_object_or_404(Devoir, pk=devoir_id, actif=True)

    # Vérifier l'accès au niveau
    classe = getattr(request.user, 'classe', None)
    niveau = getattr(classe, 'niveau', None)
    is_formateur = request.user.is_formateur or request.user.is_superuser

    if not is_formateur and niveau and devoir.chapitre.cours.niveau != niveau:
        return HttpResponseForbidden("Ce devoir ne correspond pas à votre niveau.")

    soumission = None
    form = None
    soumissions_all = None

    if is_formateur and devoir.chapitre.cours.createur == request.user:
        # Vue formateur : lister les soumissions
        soumissions_all = devoir.soumissions.select_related('etudiant').order_by('-date_soumission')
    else:
        # Vue élève : formulaire de soumission
        try:
            soumission = Soumission.objects.get(devoir=devoir, etudiant=request.user)
        except Soumission.DoesNotExist:
            soumission = None

        from .forms import SoumissionForm
        if request.method == 'POST':
            if soumission:
                # Remplacement
                form = SoumissionForm(request.POST, request.FILES, instance=soumission)
            else:
                form = SoumissionForm(request.POST, request.FILES)
            if form.is_valid():
                s = form.save(commit=False)
                s.devoir = devoir
                s.etudiant = request.user
                s.save()
                return redirect('apprentissage:devoir_detail', devoir_id=devoir.pk)
        else:
            form = SoumissionForm(instance=soumission) if soumission else SoumissionForm()

    return render(request, 'apprentissage/devoir_detail.html', {
        'devoir': devoir,
        'soumission': soumission,
        'soumissions_all': soumissions_all,
        'form': form,
        'is_formateur': is_formateur,
    })

from apprentissage.analytics import stats_formateur, stats_plateforme, stats_eleves_en_difficulte
from django.http import JsonResponse

@login_required
def formateur_analytics_dashboard(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or request.user.is_formateur):
        return HttpResponseForbidden("Accès réservé aux formateurs.")
    
    stats = stats_formateur(request.user)
    
    # Trouver les élèves en difficulté pour chaque cours
    from apprentissage.models import Cours
    mes_cours = Cours.objects.filter(createur=request.user)
    diff_students = []
    for cours in mes_cours:
        diff_students.extend(stats_eleves_en_difficulte(cours))
        
    return render(request, 'apprentissage/analytics_formateur.html', {
        'stats': stats,
        'diff_students': diff_students,
        'titre_page': "Tableau de Bord Analytics Formateur",
    })

@login_required
def formateur_analytics_data(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or request.user.is_formateur):
        return JsonResponse({'error': 'Accès interdit'}, status=403)
        
    stats = stats_formateur(request.user)
    return JsonResponse(stats)

@login_required
def admin_analytics_dashboard(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return HttpResponseForbidden("Accès réservé aux administrateurs.")
        
    stats = stats_plateforme()
    return render(request, 'apprentissage/analytics_admin.html', {
        'stats': stats,
        'titre_page': "Tableau de Bord Analytics Admin",
    })

@login_required
def admin_analytics_data(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return JsonResponse({'error': 'Accès interdit'}, status=403)
        
    stats = stats_plateforme()
    return JsonResponse(stats)


# ── Calendrier et Événements ──────────────────────────────────────────────────

@login_required
def calendrier_view(request):
    user = request.user
    if user.is_superuser or user.role == 'ADMIN':
        events = Evenement.objects.all().select_related('cours', 'classe', 'createur')
    elif user.is_formateur:
        events = Evenement.objects.filter(
            Q(createur=user) | Q(cours__createur=user)
        ).select_related('cours', 'classe', 'createur')
    else:
        # Élève
        classe = getattr(user, 'classe', None)
        niveau = getattr(classe, 'niveau', None) if classe else None
        if niveau:
            events = Evenement.objects.filter(
                Q(classe=classe) | Q(cours__niveau=niveau, cours__actif=True)
            ).select_related('cours', 'classe', 'createur')
        else:
            events = Evenement.objects.filter(
                classe__isnull=True,
                cours__isnull=True
            ).select_related('cours', 'classe', 'createur')
            
    events = events.order_by('date_debut')
    
    can_manage = user.is_superuser or user.role == 'ADMIN' or user.is_formateur
    
    return render(request, 'apprentissage/calendrier.html', {
        'events': events,
        'can_manage': can_manage,
    })


@login_required
def creer_evenement(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or request.user.is_formateur):
        return HttpResponseForbidden("Accès réservé aux formateurs et administrateurs.")
        
    from .forms import EvenementForm
    if request.method == 'POST':
        form = EvenementForm(request.POST)
        if form.is_valid():
            evt = form.save(commit=False)
            evt.createur = request.user
            evt.save()
            messages.success(request, "L'événement a été créé avec succès.")
            return redirect('apprentissage:calendrier')
    else:
        form = EvenementForm()
    return render(request, 'apprentissage/evenement_form.html', {
        'form': form,
        'titre_page': "Créer un événement",
    })


@login_required
def modifier_evenement(request, pk):
    evt = get_object_or_404(Evenement, pk=pk)
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or (request.user.is_formateur and evt.createur == request.user)):
        return HttpResponseForbidden("Vous n'êtes pas autorisé à modifier cet événement.")
        
    from .forms import EvenementForm
    if request.method == 'POST':
        form = EvenementForm(request.POST, instance=evt)
        if form.is_valid():
            form.save()
            messages.success(request, "L'événement a été modifié avec succès.")
            return redirect('apprentissage:calendrier')
    else:
        form = EvenementForm(instance=evt)
    return render(request, 'apprentissage/evenement_form.html', {
        'form': form,
        'titre_page': "Modifier l'événement",
        'evenement': evt,
    })


@login_required
@require_http_methods(['POST'])
def supprimer_evenement(request, pk):
    evt = get_object_or_404(Evenement, pk=pk)
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or (request.user.is_formateur and evt.createur == request.user)):
        return HttpResponseForbidden("Vous n'êtes pas autorisé à supprimer cet événement.")
        
    evt.delete()
    messages.success(request, "L'événement a été supprimé.")
    return redirect('apprentissage:calendrier')



