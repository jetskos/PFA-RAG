from django.db import transaction
import os
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import Q, Prefetch, Count
from .models import Cours, Chapitre, Document, Progression, ChapitreVisite, ChapitreComplete, Devoir, Soumission, Evenement, Niveau
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
    response = render(request, template_name, context)
    if request.headers.get('HX-Request') == 'true':
        response['HX-Retarget'] = '#modal-body'
    return response


def _eleve_peut_acceder_cours(user, cours):
    """Un élève ne voit que les cours de son niveau. Formateurs/admins : tout."""
    if user.is_superuser or getattr(user, 'is_formateur', False) or getattr(user, 'role', None) == 'ADMIN':
        return True
    user_niveau = getattr(getattr(user, 'classe', None), 'niveau', None)
    # Pas de niveau assigné : on ne bloque pas (comportement historique du catalogue).
    return user_niveau is None or cours.niveau_id == user_niveau.id


def _notifier_nouveau_cours(cours):
    """Notifie les élèves du niveau qu'un cours vient d'être publié. Best-effort.

    À n'appeler que lorsque le cours est réellement visible (actif=True) : sinon
    on notifie pour un brouillon vide (voir wizard de création)."""
    if not cours.actif:
        return
    try:
        from accounts.models import Utilisateur
        from accounts.notifications import notifier
        eleves = Utilisateur.objects.filter(
            role='ELEVE', is_active=True, classe__niveau=cours.niveau,
        )
        for eleve in eleves:
            notifier(
                destinataire=eleve,
                type='NOUVEAU_COURS',
                titre=_("Nouveau cours : %(cours)s") % {'cours': cours.titre},
                message=_("Le cours « %(cours)s » est disponible pour votre niveau %(niveau)s.")
                        % {'cours': cours.titre, 'niveau': cours.niveau.nom},
                url=reverse('apprentissage:detail_cours', args=[cours.id]),
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Notification « nouveau cours » échouée")


def _get_video_context(chapitre):
    """
    Calcule comment afficher la vidéo d'un chapitre.

    Hybride en ligne/hors-ligne : si aucune connexion internet n'est détectée,
    on bascule automatiquement sur le fichier MP4 local (video_fichier) plutôt
    que sur le lien YouTube/Vimeo/direct — utile pour les élèves sans réseau.
    """
    from core.utils import has_internet

    context = {
        'is_offline_video': False,
        'is_direct_video': False,
        'is_youtube': False,
        'is_vimeo': False,
        'vimeo_embed_url': '',
        'is_unavailable_offline': False,
        'activer_hls': False,
    }
    
    try:
        from accounts.models import ConfigurationSysteme
        config = ConfigurationSysteme.objects.first()
        if config:
            context['activer_hls'] = config.activer_hls
    except Exception:
        pass

    online = has_internet(host="www.youtube.com", port=443)

    if not online and chapitre.video_fichier:
        context['is_offline_video'] = True
        return context

    url = chapitre.url_video or ''
    url_lower = url.lower()

    if not url:
        # Pas de lien en ligne : se rabattre sur le fichier local s'il existe.
        if chapitre.video_fichier:
            context['is_offline_video'] = True
        return context

    if not online:
        # Un lien existe mais on ne peut pas le charger sans connexion,
        # et aucun fichier local n'a été fourni en secours.
        context['is_unavailable_offline'] = True
        return context

    context['is_direct_video'] = any(url_lower.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov'])
    context['is_youtube'] = 'youtube.com' in url_lower or 'youtu.be' in url_lower
    context['is_vimeo'] = 'vimeo.com' in url_lower

    if context['is_vimeo']:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            parts = parsed.path.strip('/').split('/')
            video_id = ''
            for part in reversed(parts):
                if part.isdigit():
                    video_id = part
                    break
            context['vimeo_embed_url'] = f"https://player.vimeo.com/video/{video_id}" if video_id else url
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Erreur lors du parsing de l'URL Vimeo ({url}): {e}")
            context['vimeo_embed_url'] = url

    return context


@login_required
def espace_formateur(request):
    """Espace dédié aux formateurs pour gérer leurs cours."""
    # Réservé aux formateurs (les admins/superusers passent aussi).
    if not request.user.is_formateur and request.user.role != 'ADMIN' and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(_("Accès réservé aux formateurs."))

    # Si le champ createur est null pour certains cours, on filtre proprement
    mes_cours = Cours.objects.filter(createur=request.user).order_by('-date_creation')

    # Récupérer les devoirs créés par le formateur avec le nombre de soumissions
    from django.db.models import Count, Q
    devoirs = Devoir.objects.filter(createur=request.user).select_related('chapitre', 'chapitre__cours').annotate(
        total_soumissions=Count('soumissions'),
        soumissions_a_noter=Count('soumissions', filter=Q(soumissions__note__isnull=True))
    ).order_by('-date_creation')
    # Récupérer l'historique des exports
    from .models import ExportJob
    export_jobs = ExportJob.objects.filter(formateur=request.user).order_by('-date_creation')

    context = {
        'mes_cours': mes_cours,
        'devoirs': devoirs,
        'export_jobs': export_jobs,
    }

    return render(request, 'apprentissage/espace_formateur.html', context)



@login_required
@require_http_methods(['GET', 'POST'])
def nouveau_cours(request):
    """Créer un nouveau cours pour le formateur connecté. Réservé aux FORMATEURS."""
    if not (request.user.is_formateur or request.user.is_superuser):
        return HttpResponseForbidden(_("Accès réservé aux formateurs."))
    if hasattr(request.user, 'role') and request.user.role == 'ADMIN':
        return_url = reverse('apprentissage:liste_cours')
    else:
        return_url = reverse('apprentissage:espace_formateur')

    if request.method == 'POST':
        form = CoursForm(request.POST, request.FILES)
        if form.is_valid():
            cours = form.save(commit=False)
            cours.createur = request.user
            cours.save()
            # Notifie seulement si le cours est publié (pas pour un brouillon).
            _notifier_nouveau_cours(cours)
            return redirect(return_url)
    else:
        form = CoursForm()

    return render(request, 'apprentissage/cours_form.html', {
        'form': form,
        'return_url': return_url
    })


@login_required
@FormateurCoursRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def editer_cours(request, pk):
    """Modifier un cours appartenant au formateur connecté."""
    cours = get_object_or_404(Cours, pk=pk)

    if hasattr(request.user, 'role') and request.user.role == 'ADMIN':
        return_url = reverse('apprentissage:liste_cours')
    else:
        return_url = reverse('apprentissage:espace_formateur')

    if request.method == 'POST':
        etait_actif = cours.actif
        form = CoursForm(request.POST, request.FILES, instance=cours)
        if form.is_valid():
            cours = form.save()
            # Publication d'un brouillon (actif False -> True) : on notifie les élèves.
            if cours.actif and not etait_actif:
                _notifier_nouveau_cours(cours)
            return redirect(return_url)
    else:
        form = CoursForm(instance=cours)

    return render(request, 'apprentissage/cours_form.html', {
        'form': form,
        'return_url': return_url
    })


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
        form = ChapitreForm(request.POST, request.FILES)
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

    if request.headers.get('HX-Request') == 'true' and request.headers.get('HX-Target') != 'zone-principale':
        return render(request, 'apprentissage/partials/chapitre_detail.html', context)
    return render(request, 'apprentissage/gerer_chapitre.html', context)


@login_required
@FormateurChapitreRequiredMixin.as_decorator()
@require_http_methods(['GET', 'POST'])
def editer_chapitre(request, chapitre_id):
    """Modifier un chapitre appartenant au formateur connecté."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id)
    cours = chapitre.cours

    if request.method == 'POST':
        form = ChapitreForm(request.POST, request.FILES, instance=chapitre)
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
    niveau_filter_id = request.GET.get('niveau_id', '').strip()
    
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

    # Application du filtre par niveau si présent
    if niveau_filter_id:
        cours_list = cours_list.filter(niveau_id=niveau_filter_id)
        
    cours_list = cours_list.order_by('-date_creation').distinct()
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(cours_list, 12) # 12 items per page for grids
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Récupérer les niveaux pour le filtre
    niveaux = Niveau.objects.all()
    
    # HTMX Partial Rendering for search/filters/pagination
    if request.headers.get('HX-Target') == 'catalog-grid':
        return render(request, 'apprentissage/partials/liste_cours.html', {
            'cours_list': page_obj,
            'page_obj': page_obj
        })
    
    context = {
        'cours_list': page_obj,
        'page_obj': page_obj,
        'niveaux': niveaux,
        'titre_page': _('Catalogue des cours'),
        'q': q,
        'niveau_filter_id': niveau_filter_id
    }
    return render(request, 'apprentissage/liste_cours.html', context)


@login_required
def detail_cours(request, cours_id):
    """Affiche un cours avec ses chapitres et documents groupés par type."""
    cours = get_object_or_404(Cours, id=cours_id)

    # Si le cours est inactif, seul le superuser ou le formateur créateur peut y accéder
    if not cours.actif:
        if not request.user.is_superuser:
            if not getattr(request.user, 'is_formateur', False) or cours.createur != request.user:
                return render(request, 'apprentissage/cours_inactif.html', status=403)

    # Sécurité : empêcher un étudiant d'accéder à un cours hors de son niveau
    if request.user.is_authenticated and not (request.user.is_superuser or request.user.is_formateur):
        classe = getattr(request.user, 'classe', None)
        user_niveau = getattr(classe, 'niveau', None)
        if user_niveau and cours.niveau_id != user_niveau.id:
            return HttpResponseForbidden(_("Ce cours ne correspond pas à votre niveau actuel."))
    
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
    video_ctx = {
        'is_offline_video': False, 'is_direct_video': False, 'is_youtube': False,
        'is_vimeo': False, 'vimeo_embed_url': '', 'is_unavailable_offline': False,
    }
    chapitre_precedent = None
    chapitre_suivant = None
    chapitre_initial_is_complete = False

    if chapitres.exists():
        chapitre_initial = chapitres.first()
        chapitre_precedent = None
        chapitre_suivant = chapitres.filter(ordre__gt=chapitre_initial.ordre).order_by('ordre').first()

        video_ctx = _get_video_context(chapitre_initial)

        if request.user.is_authenticated:
            from tuteur_ia.models import SessionAssistant
            session_assistant, _sa_created = SessionAssistant.objects.get_or_create(
                etudiant=request.user,
                chapitre=chapitre_initial
            )
            chapitre_initial_is_complete = ChapitreComplete.objects.filter(
                etudiant=request.user,
                chapitre=chapitre_initial
            ).exists()
            
            progression_obj = Progression.objects.filter(
                etudiant=request.user,
                cours=cours
            ).first()
            progression_totale = progression_obj.pourcentage if progression_obj else 0
        else:
            progression_totale = 0
    else:
        progression_totale = 0

    context = {
        'cours': cours,
        'chapitres_data': chapitres_data,
        'can_edit_documents': False,
        'chapitre_initial_assistant': session_assistant,
        'chapitre_initial_is_offline_video': video_ctx['is_offline_video'],
        'chapitre_initial_is_direct_video': video_ctx['is_direct_video'],
        'chapitre_initial_is_youtube': video_ctx['is_youtube'],
        'chapitre_initial_is_vimeo': video_ctx['is_vimeo'],
        'chapitre_initial_vimeo_embed_url': video_ctx['vimeo_embed_url'],
        'chapitre_initial_is_unavailable_offline': video_ctx['is_unavailable_offline'],
        'chapitre_initial_precedent': chapitre_precedent,
        'chapitre_initial_suivant': chapitre_suivant,
        'chapitre_initial_is_complete': chapitre_initial_is_complete,
        'progression_totale': progression_totale,
    }
    
    if request.headers.get('HX-Request') == 'true' and request.headers.get('HX-Target') != 'zone-principale':
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

    # Même règle de niveau que detail_cours : un élève ne lit pas un chapitre
    # d'un cours hors de son niveau (accès direct par URL).
    if not _eleve_peut_acceder_cours(request.user, cours):
        return HttpResponseForbidden(_("Ce cours ne correspond pas à votre niveau actuel."))

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
    
    # Analyse de la vidéo (hybride en ligne/hors-ligne)
    video_ctx = _get_video_context(chapitre)

    # Charger/Créer la session RAG Assistant
    session_assistant = None
    if request.user.is_authenticated:
        from tuteur_ia.models import SessionAssistant
        session_assistant, _sa_created = SessionAssistant.objects.get_or_create(
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
        'is_offline_video': video_ctx['is_offline_video'],
        'is_direct_video': video_ctx['is_direct_video'],
        'is_youtube': video_ctx['is_youtube'],
        'is_vimeo': video_ctx['is_vimeo'],
        'vimeo_embed_url': video_ctx['vimeo_embed_url'],
        'is_unavailable_offline': video_ctx['is_unavailable_offline'],
        'session_assistant': session_assistant,
    }
    
    if request.headers.get('HX-Request') == 'true' and request.headers.get('HX-Target') != 'zone-principale':
        return render(request, 'apprentissage/partials/detail_chapitre.html', context)
    
    return render(request, 'apprentissage/detail_chapitre.html', context)



@login_required
def telecharger_document(request, document_id):
    """Télécharge le PDF d'un document — connecté + niveau de l'élève respecté."""
    document = get_object_or_404(
        Document.objects.select_related('chapitre__cours'),
        id=document_id, actif=True,
    )

    if not _eleve_peut_acceder_cours(request.user, document.chapitre.cours):
        return HttpResponseForbidden(_("Ce cours ne correspond pas à votre niveau actuel."))

    if not document.fichier_pdf:
        return HttpResponse(_('Fichier non disponible'), status=404)

    from django.http import FileResponse
    return FileResponse(
        document.fichier_pdf.open('rb'),
        as_attachment=True,
        filename=f"{document.titre}.pdf",
        content_type='application/pdf',
    )


@login_required
@require_http_methods(['POST'])
def valider_chapitre(request, chapitre_id):
    """Marque un chapitre comme validé pour l'étudiant connecté."""
    chapitre = get_object_or_404(Chapitre, pk=chapitre_id, actif=True)
    
    # Vérification du QCM
    from tuteur_ia.models import SessionQCM
    has_passed_qcm = SessionQCM.objects.filter(
        etudiant=request.user, 
        chapitre=chapitre, 
        statut='TERMINEE'
    ).exists()
    
    if not has_passed_qcm:
        from django.contrib import messages
        messages.warning(request, _("Vous devez d'abord réussir le QCM de ce chapitre pour le marquer comme terminé."))
        response = HttpResponse(status=204)
        from django.urls import reverse
        response['HX-Redirect'] = reverse('apprentissage:detail_chapitre', args=[chapitre.cours.id, chapitre.id])
        return response
    
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

    search_query = request.GET.get('q', '').lower()
    statut_filter = request.GET.get('statut', 'tous')

    cours_filtres = []
    for c_data in bulletin.get('cours', []):
        cours_obj = c_data['cours']
        
        # Filtre par recherche de titre
        if search_query and search_query not in cours_obj.titre.lower():
            continue
            
        # Filtre par statut des chapitres
        if statut_filter != 'tous':
            chapitres_filtres = []
            for ch in c_data['chapitres']:
                statut_ch = ch.get('statut', 'NON_TENTE').upper()
                if statut_filter == 'reussi' and statut_ch == 'REUSSI':
                    chapitres_filtres.append(ch)
                elif statut_filter == 'echec' and statut_ch == 'ECHOUE':
                    chapitres_filtres.append(ch)
                elif statut_filter == 'non_tente' and statut_ch == 'NON_TENTE':
                    chapitres_filtres.append(ch)
            
            c_data['chapitres'] = chapitres_filtres
            # Si le cours ne contient plus aucun chapitre correspondant, on l'ignore
            if not chapitres_filtres:
                continue

        cours_filtres.append(c_data)

    bulletin['cours'] = cours_filtres

    return render(request, 'apprentissage/mes_notes.html', {
        'bulletin': bulletin,
        'titre_page': _('Mon carnet de notes'),
        'search_query': search_query,
        'statut_filter': statut_filter,
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
        return HttpResponseForbidden(_("Accès réservé aux formateurs."))

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
        'titre_page': _('Notes de mes étudiants'),
    })


@login_required
def exporter_notes_classe_csv(request):
    """Exporte les notes de tous les élèves des cours du formateur en CSV avec support du filtre de classe."""
    if not (request.user.is_formateur or request.user.is_superuser):
        return HttpResponseForbidden(_("Accès réservé aux formateurs."))

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
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Erreur lors de l'envoi de la notification pour le devoir {devoir.pk}: {e}")

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
                    titre=_("Devoir corrigé : %(devoir)s") % {'devoir': devoir.titre},
                    message=_("Votre devoir '%(devoir)s' a été corrigé. Note : %(note)s/%(max)s.") % {'devoir': devoir.titre, 'note': s.note, 'max': devoir.note_max},
                    url=reverse('apprentissage:devoir_detail', args=[devoir.pk])
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Erreur lors de l'envoi de la notification de correction pour la soumission {soumission.pk}: {e}")

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
    """Liste tous les devoirs actifs disponibles pour l'étudiant connecté, groupés par cours."""
    from django.utils import timezone
    from collections import defaultdict

    # Filtrer par niveau si l'étudiant a une classe
    classe = getattr(request.user, 'classe', None)
    niveau = getattr(classe, 'niveau', None)

    devoirs_qs = Devoir.objects.filter(actif=True).select_related(
        'chapitre', 'chapitre__cours', 'chapitre__cours__niveau'
    ).order_by('chapitre__cours__titre', '-date_creation')

    # N'afficher que les devoirs liés aux cours que l'étudiant a commencés (via Progression)
    devoirs_qs = devoirs_qs.filter(chapitre__cours__progressions__etudiant=request.user)

    # Filtre par statut (query param ?statut=)
    filtre_statut = request.GET.get('statut', 'tous')

    # Annoter avec la soumission de l'étudiant si elle existe
    soumissions_map = {
        str(s.devoir_id): s
        for s in Soumission.objects.filter(etudiant=request.user)
    }

    now = timezone.now()

    # Construire les items avec statut calculé
    devoirs_data = []
    for devoir in devoirs_qs:
        soumission = soumissions_map.get(str(devoir.id))
        # Calcul statut
        if soumission:
            if soumission.est_corrigee:
                statut = 'corrige'
            else:
                statut = 'soumis'
        else:
            if devoir.date_limite and devoir.date_limite < now:
                statut = 'depasse'
            else:
                statut = 'a_rendre'

        devoirs_data.append({
            'devoir': devoir,
            'soumission': soumission,
            'statut': statut,
        })

    # Appliquer le filtre statut
    if filtre_statut != 'tous':
        devoirs_data = [d for d in devoirs_data if d['statut'] == filtre_statut]

    # Grouper par cours
    cours_map = defaultdict(list)
    for item in devoirs_data:
        cours_key = item['devoir'].chapitre.cours
        cours_map[cours_key].append(item)

    devoirs_par_cours = list(cours_map.items())  # [(cours_obj, [items...]), ...]

    # Stats pour les onglets
    total = len(devoirs_data) if filtre_statut != 'tous' else len([d for d in devoirs_data])
    # Recompute stats always from full data
    all_items = []
    for devoir in Devoir.objects.filter(actif=True).select_related('chapitre', 'chapitre__cours'):
        soumission = soumissions_map.get(str(devoir.id))
        if soumission:
            statut = 'corrige' if soumission.est_corrigee else 'soumis'
        else:
            statut = 'depasse' if (devoir.date_limite and devoir.date_limite < now) else 'a_rendre'
        all_items.append(statut)

    stats = {
        'tous': len(all_items),
        'a_rendre': all_items.count('a_rendre'),
        'soumis': all_items.count('soumis'),
        'corrige': all_items.count('corrige'),
        'depasse': all_items.count('depasse'),
    }

    return render(request, 'apprentissage/devoirs_liste.html', {
        'devoirs_par_cours': devoirs_par_cours,
        'devoirs_data': devoirs_data,
        'filtre_statut': filtre_statut,
        'stats': stats,
        'now': now,
        'titre_page': _('Mes devoirs'),
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
        return HttpResponseForbidden(_("Ce devoir ne correspond pas à votre niveau."))

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
        if request.method == 'POST' and not (soumission and soumission.est_corrigee):
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

                # Notifier le formateur créateur du devoir
                if devoir.createur:
                    try:
                        from accounts.notifications import notifier
                        notifier(
                            destinataire=devoir.createur,
                            type='NOUVELLE_INSCRIPTION',
                            titre=f"Devoir soumis : {devoir.titre}",
                            message=f"L'étudiant {request.user.get_full_name()} a soumis son devoir '{devoir.titre}'.",
                            url=reverse('apprentissage:devoir_detail', args=[devoir.pk])
                        )
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Erreur lors de l'envoi de la notification de soumission de devoir pour {devoir.pk}: {e}")

                return redirect('apprentissage:devoir_detail', devoir_id=devoir.pk)
        else:
            form = SoumissionForm(instance=soumission) if soumission else SoumissionForm()
            if soumission and soumission.est_corrigee:
                for field in form.fields.values():
                    field.disabled = True

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
        return HttpResponseForbidden(_("Accès réservé aux formateurs."))
    
    stats = stats_formateur(request.user)
    
    # Trouver les élèves en difficulté pour chaque cours
    from apprentissage.models import Cours
    import json
    mes_cours = Cours.objects.filter(createur=request.user)
    diff_students = []
    for cours in mes_cours:
        diff_students.extend(stats_eleves_en_difficulte(cours))
    
    # Pre-serialize chart data as JSON to avoid Django template hyphen issue
    chart_labels = []
    chart_completion = []
    chart_rep_0_25 = 0
    chart_rep_25_50 = 0
    chart_rep_50_75 = 0
    chart_rep_75_100 = 0
    for item in stats.get('details_cours', []):
        chart_labels.append(item['titre'][:30])
        chart_completion.append(item['taux_completion_moyen'])
        rep = item.get('repartition', {})
        chart_rep_0_25   += rep.get('0-25', 0)
        chart_rep_25_50  += rep.get('25-50', 0)
        chart_rep_50_75  += rep.get('50-75', 0)
        chart_rep_75_100 += rep.get('75-100', 0)

    chart_data_json = json.dumps({
        'labels': chart_labels,
        'completion': chart_completion,
        'repartition': [chart_rep_0_25, chart_rep_25_50, chart_rep_50_75, chart_rep_75_100],
    })

    return render(request, 'apprentissage/analytics_formateur.html', {
        'stats': stats,
        'diff_students': diff_students,
        'titre_page': _("Tableau de Bord Analytics Formateur"),
        'chart_data_json': chart_data_json,
    })


@login_required
def formateur_analytics_data(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or request.user.is_formateur):
        return JsonResponse({'error': _("Accès interdit")}, status=403)
        
    stats = stats_formateur(request.user)
    return JsonResponse(stats)

@login_required
def admin_analytics_dashboard(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return HttpResponseForbidden(_("Accès réservé aux administrateurs."))
        
    stats = stats_plateforme()
    return render(request, 'apprentissage/analytics_admin.html', {
        'stats': stats,
        'titre_page': _("Tableau de Bord Analytics Admin"),
    })

@login_required
def admin_analytics_data(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return JsonResponse({'error': _("Accès interdit")}, status=403)
        
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
def calendrier_events_json(request):
    from django.http import JsonResponse
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
            
    events_data = []
    can_manage_global = user.is_superuser or user.role == 'ADMIN' or user.is_formateur
    
    color_map = {
        'ECHEANCE_DEVOIR': '#ef4444',
        'SESSION':         '#3b82f6',
        'EXAMEN':          '#f59e0b',
        'AUTRE':           '#10b981',
    }

    for ev in events:
        can_manage_ev = can_manage_global and (user.is_superuser or user.role == 'ADMIN' or ev.createur == user)
        events_data.append({
            'id': str(ev.id),
            'title': ev.titre,
            'start': ev.date_debut.isoformat() if ev.date_debut else None,
            'end': ev.date_fin.isoformat() if ev.date_fin else None,
            'backgroundColor': color_map.get(ev.type, '#10b981'),
            'extendedProps': {
                'rawType': ev.type,
                'type': ev.get_type_display(),
                'description': ev.description,
                'cours': ev.cours.titre if ev.cours else None,
                'classe': ev.classe.nom if ev.classe else None,
                'can_manage': can_manage_ev,
                'edit_url': reverse('apprentissage:modifier_evenement', args=[ev.id]) if can_manage_ev else '',
                'delete_url': reverse('apprentissage:supprimer_evenement', args=[ev.id]) if can_manage_ev else '',
            }
        })
    return JsonResponse(events_data, safe=False)

@login_required
def creer_evenement(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or request.user.is_formateur):
        return HttpResponseForbidden(_("Accès réservé aux formateurs et administrateurs."))
        
    from .forms import EvenementForm
    if request.method == 'POST':
        form = EvenementForm(request.POST, user=request.user)
        if form.is_valid():
            evt = form.save(commit=False)
            evt.createur = request.user
            evt.save()
            messages.success(request, _("L'événement a été créé avec succès."))
            return redirect('apprentissage:calendrier')
    else:
        form = EvenementForm(user=request.user)
    return render(request, 'apprentissage/evenement_form.html', {
        'form': form,
        'titre_page': _("Créer un événement"),
    })


@login_required
def modifier_evenement(request, pk):
    evt = get_object_or_404(Evenement, pk=pk)
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or (request.user.is_formateur and evt.createur == request.user)):
        return HttpResponseForbidden(_("Vous n'êtes pas autorisé à modifier cet événement."))
        
    from .forms import EvenementForm
    if request.method == 'POST':
        form = EvenementForm(request.POST, instance=evt, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("L'événement a été modifié avec succès."))
            return redirect('apprentissage:calendrier')
    else:
        form = EvenementForm(instance=evt, user=request.user)
    return render(request, 'apprentissage/evenement_form.html', {
        'form': form,
        'titre_page': _("Modifier l'événement"),
        'evenement': evt,
    })


@login_required
@require_http_methods(['POST'])
def supprimer_evenement(request, pk):
    evt = get_object_or_404(Evenement, pk=pk)
    if not (request.user.is_superuser or request.user.role == 'ADMIN' or (request.user.is_formateur and evt.createur == request.user)):
        return HttpResponseForbidden(_("Vous n'êtes pas autorisé à supprimer cet événement."))
        
    evt.delete()
    messages.success(request, _("L'événement a été supprimé."))
    return redirect('apprentissage:calendrier')

import json
from django.http import JsonResponse
from .models import ExportJob

@login_required
@require_http_methods(['POST'])
def export_multiple_courses_view(request):
    """Lance la tâche d'exportation (en arrière-plan) pour plusieurs cours."""
    if not request.user.is_formateur and request.user.role != 'ADMIN':
        return JsonResponse({'status': 'error', 'message': _("Non autorisé.")}, status=403)

    try:
        data = json.loads(request.body)
        course_ids = data.get('course_ids', [])

        if not course_ids:
            return JsonResponse({'status': 'error', 'message': _("Aucun cours sélectionné.")})
            
        jobs_created = []
        for cid in course_ids:
            cours = get_object_or_404(Cours, pk=cid)
            
            # Vérifier les droits
            if not request.user.is_superuser and request.user.role != 'ADMIN' and cours.createur != request.user:
                continue
                
            job = ExportJob.objects.create(formateur=request.user, cours=cours)
            
            from .tasks import export_course_task
            export_course_task.delay(str(job.id))
            
            jobs_created.append({'id': str(job.id), 'cours_titre': cours.titre})
            
        if not jobs_created:
            return JsonResponse({'status': 'error', 'message': _("Aucun cours valide n'a pu être exporté.")})

        return JsonResponse({'status': 'success', 'jobs': jobs_created, 'message': _("%(count)s export(s) lancé(s).") % {'count': len(jobs_created)}})
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Échec du lancement de l'export multiple")
        return JsonResponse({'status': 'error', 'message': _("Une erreur est survenue pendant l'export.")}, status=500)

@login_required
def check_export_status_view(request, job_id):
    """Vérifie l'état d'un export."""
    job = get_object_or_404(ExportJob, pk=job_id, formateur=request.user)
    data = {
        'status': job.status,
        'erreur': job.erreur,
        'url': job.fichier_zip.url if job.fichier_zip else None
    }
    return JsonResponse(data)

@login_required
def check_import_status_view(request, job_id):
    """Vérifie l'état d'un import."""
    from .models import ImportJob
    from django.utils import timezone
    from datetime import timedelta
    job = get_object_or_404(ImportJob, pk=job_id, formateur=request.user)

    # Job bloqué : un import interrompu (onglet fermé, process tué) reste en état
    # non terminal pour toujours. Au-delà de 15 min, on le déclare échoué.
    if job.status not in ('TERMINE', 'FAILED') and job.date_creation < timezone.now() - timedelta(minutes=15):
        job.status = 'FAILED'
        job.erreur = job.erreur or "Import interrompu (délai dépassé)."
        job.date_fin = timezone.now()
        job.save(update_fields=['status', 'erreur', 'date_fin'])

    data = {
        'status': job.status,
        'erreur': job.erreur,
        'titre_cours': job.titre_cours
    }
    return JsonResponse(data)

import os
from django.core.files.storage import FileSystemStorage

@login_required
@require_http_methods(['POST'])
def import_multiple_courses_view(request):
    """Reçoit des fichiers ZIP et lance les tâches d'importation en arrière-plan."""
    if not request.user.is_formateur and request.user.role != 'ADMIN':
        return JsonResponse({'status': 'error', 'message': _("Non autorisé.")}, status=403)

    try:
        files = request.FILES.getlist('zip_files')
        if not files:
            return JsonResponse({'status': 'error', 'message': _("Aucun fichier reçu.")})
            
        # Sauvegarder temporairement les fichiers ZIP
        fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'imports', 'temp'))
        saved_files = []
        for f in files:
            filename = fs.save(f.name, f)
            saved_files.append(os.path.join(fs.location, filename))
            
        # Créer le job d'importation
        from .models import ImportJob
        import_job = ImportJob.objects.create(formateur=request.user)

        # Lancer la tâche Celery pour l'importation
        from .tasks import import_courses_task
        import_courses_task.delay(str(import_job.id), request.user.id, saved_files)

        return JsonResponse({'status': 'success', 'job_id': str(import_job.id), 'message': _("%(count)s fichier(s) en cours d'importation.") % {'count': len(saved_files)}})
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Échec du lancement de l'import multiple")
        return JsonResponse({'status': 'error', 'message': _("Une erreur est survenue pendant l'import.")}, status=500)


# ── Mises à jour reçues par satellite (carrousel FLUTE) ───────────────────────

def _is_admin(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) == 'ADMIN')


def _render_satellite_card(request):
    """Scanne la boîte satellite et renvoie la carte du tableau de bord (partial HTMX)."""
    from .satellite import scan_inbox, reconcile_statuses
    from .models import SatelliteUpdate

    error = None
    pending = SatelliteUpdate.objects.none()
    try:
        reconcile_statuses()
        pending = list(scan_inbox().order_by('detected_at'))
    except Exception as exc:  # dossier illisible, disque plein… : on n'écroule pas le dashboard
        import logging
        logging.getLogger(__name__).warning("Scan satellite impossible : %s", exc, exc_info=True)
        error = _("Boîte de réception satellite inaccessible.")

    recent = (
        SatelliteUpdate.objects
        .exclude(status='DETECTED')
        .order_by('-applied_at', '-detected_at')[:5]
    )
    return render(request, 'apprentissage/partials/satellite_updates_card.html', {
        'satellite_pending': pending,
        'satellite_recent': recent,
        'satellite_error': error,
    })


@login_required
def satellite_updates_card(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden(_("Accès réservé aux administrateurs."))
    return _render_satellite_card(request)


@login_required
@require_http_methods(['POST'])
def apply_satellite_update(request, update_id):
    if not _is_admin(request.user):
        return HttpResponseForbidden(_("Accès réservé aux administrateurs."))
    from .satellite import apply_update
    from .models import SatelliteUpdate

    update = get_object_or_404(SatelliteUpdate, pk=update_id, status='DETECTED')
    apply_update(update, request.user)
    messages.success(request, _("Mise à jour « %(nom)s » : import lancé.") % {'nom': update.logical_name})
    return _render_satellite_card(request)


@login_required
@require_http_methods(['POST'])
def apply_all_satellite_updates(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden(_("Accès réservé aux administrateurs."))
    from .satellite import apply_update, scan_inbox
    from .models import SatelliteUpdate

    count = 0
    for update in list(scan_inbox().order_by('detected_at')):
        apply_update(update, request.user)
        count += 1
    if count:
        messages.success(request, _("%(count)s mise(s) à jour satellite : import lancé.") % {'count': count})
    return _render_satellite_card(request)
 
