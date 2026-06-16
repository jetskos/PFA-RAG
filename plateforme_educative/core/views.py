from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apprentissage.models import Cours
from accounts.models import Classe, Niveau
from logistics.forms import DemandeMaterielForm
from logistics.models import DemandeMateriel
from .forms import NiveauForm, ClasseForm, PendingStudentActivationForm

Utilisateur = get_user_model()


def home_view(request):
    """Affiche la page d'accueil avec la progression de l'étudiant si connecté."""
    from apprentissage.models import Cours, Chapitre, Document

    context = {
        'stats': {
            'cours': Cours.objects.filter(actif=True).count(),
            'chapitres': Chapitre.objects.filter(actif=True).count(),
            'documents': Document.objects.filter(actif=True).count(),
        }
    }
    
    if request.user.is_authenticated:
        from apprentissage.models import Progression
        progressions = Progression.objects.filter(etudiant=request.user).order_by('-date_derniere_consultation')[:3]

        if progressions:
            context['resume_url'] = reverse('apprentissage:detail_cours', args=[progressions[0].cours.id])
        else:
            context['resume_url'] = reverse('apprentissage:liste_cours')
        
        cours_en_cours = [
            {
                'titre': p.cours.titre,
                'chapitre_actuel': f"{p.chapitres_valides.count()}/{p.cours.chapitres.count()} chapitres",
                'progression': p.pourcentage
                , 'url': reverse('apprentissage:detail_cours', args=[p.cours.id])
            }
            for p in progressions
        ]
        context['cours_en_cours'] = cours_en_cours
    
    return render(request, 'core/home.html', context)


def _admin_dashboard_context():
    pending_students = Utilisateur.objects.filter(statut_compte='PENDING').select_related('classe__niveau').order_by('date_creation')
    pending_rows = [
        {
            'user': student,
            'form': PendingStudentActivationForm(initial={'student_id': student.id}),
        }
        for student in pending_students
    ]
    return {
        'niveaux': Niveau.objects.all().order_by('ordre', 'nom'),
        'classes': Classe.objects.select_related('niveau').all().order_by('niveau__ordre', 'nom'),
        'pending_students': pending_students,
        'pending_rows': pending_rows,
        'pending_demandes': DemandeMateriel.objects.filter(statut='PENDING').select_related('formateur', 'equipement', 'atelier_cible').order_by('-date_creation'),
        'niveau_form': NiveauForm(),
        'classe_form': ClasseForm(),
        'niveau_editor_form': None,
        'niveau_editor_title': '',
    }


def _render_admin_structure(request, context=None, status=200, active_tab='niveaux'):
    render_context = _admin_dashboard_context()
    render_context['active_tab'] = active_tab
    if context:
        render_context.update(context)
    return render(request, 'core/partials/admin_structure.html', render_context, status=status)


def _formateur_dashboard_context(request):
    mes_cours = Cours.objects.filter(createur=request.user).select_related('niveau').order_by('-date_creation')
    mes_demandes = DemandeMateriel.objects.filter(formateur=request.user).select_related(
        'equipement',
        'atelier_cible',
    ).order_by('-date_creation')
    return {
        'mes_cours': mes_cours,
        'mes_demandes': mes_demandes,
        'demande_form': DemandeMaterielForm(),
    }


def _render_formateur_structure(request, context=None, status=200):
    render_context = _formateur_dashboard_context(request)
    if context:
        render_context.update(context)
    return render(request, 'core/partials/formateur_structure.html', render_context, status=status)


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not getattr(user, 'is_active', False):
                return HttpResponseForbidden('Votre compte est en attente de validation.')
            if user.role not in allowed_roles and not user.is_superuser:
                return HttpResponseForbidden('Accès refusé.')
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = ()

    def test_func(self):
        user = self.request.user
        if not getattr(user, 'is_active', False):
            return False
        return user.is_superuser or user.role in self.allowed_roles


def dashboard_router(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    if not getattr(request.user, 'is_active', False):
        return HttpResponseForbidden('Votre compte est en attente de validation.')

    if request.user.is_superuser or request.user.role == 'ADMIN':
        return redirect('dashboard_admin')
    if request.user.role == 'FORMATEUR':
        return redirect('dashboard_formateur')
    return redirect('dashboard_student')


@role_required('ADMIN')
def admin_dashboard_view(request):
    tab = request.GET.get('tab', 'niveaux')
    context = {
        'role': 'ADMIN',
        'active_tab': tab,
        **_admin_dashboard_context(),
    }
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/admin_structure.html', context)
    return render(request, 'core/dashboard_admin.html', context)


@role_required('FORMATEUR')
def formateur_dashboard_view(request):
    tab = request.GET.get('tab', 'all')
    context = {
        'role': 'FORMATEUR',
        'active_tab': tab,
        **_formateur_dashboard_context(request),
    }
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/formateur_structure.html', context)
    return render(request, 'core/dashboard_formateur.html', context)


@role_required('ELEVE')
def student_dashboard_view(request):
    classe = getattr(request.user, 'classe', None)
    niveau = getattr(classe, 'niveau', None) if classe else None
    if niveau:
        mes_cours = Cours.objects.filter(niveau=niveau, actif=True).order_by('titre')
    else:
        mes_cours = Cours.objects.none()

    return render(request, 'core/dashboard_student.html', {
        'role': 'ELEVE',
        'classe': classe,
        'niveau': niveau,
        'mes_cours': mes_cours,
    })


@role_required('ADMIN')
@require_http_methods(['GET', 'POST'])
def create_niveau_view(request):
    if request.method == 'POST':
        form = NiveauForm(request.POST)
        if form.is_valid():
            form.save()
            return _render_admin_structure(request, active_tab='niveaux')
    else:
        form = NiveauForm()

    return _render_admin_structure(request, {'niveau_form': form}, status=400 if request.method == 'POST' else 200, active_tab='niveaux')


@role_required('ADMIN')
@require_http_methods(['GET', 'POST'])
def edit_niveau_view(request, niveau_id):
    niveau = get_object_or_404(Niveau, pk=niveau_id)

    if request.method == 'POST':
        form = NiveauForm(request.POST, instance=niveau)
        if form.is_valid():
            form.save()
            return _render_admin_structure(request, active_tab='niveaux')
    else:
        form = NiveauForm(instance=niveau)

    return render(request, 'core/partials/niveau_form.html', {
        'niveau_form': form,
        'niveau': niveau,
        'submit_label': 'Enregistrer',
        'cancel_label': 'Annuler',
        'action_url': reverse('dashboard_admin_edit_niveau', args=[niveau.id]),
    }, status=400 if request.method == 'POST' else 200)


@role_required('ADMIN')
@require_http_methods(['GET', 'POST'])
def create_classe_view(request):
    if request.method == 'POST':
        form = ClasseForm(request.POST)
        if form.is_valid():
            form.save()
            return _render_admin_structure(request, active_tab='classes')
    else:
        form = ClasseForm()

    return _render_admin_structure(request, {'classe_form': form}, status=400 if request.method == 'POST' else 200, active_tab='classes')


@role_required('ADMIN')
@require_http_methods(['GET', 'POST'])
def edit_classe_view(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)

    if request.method == 'POST':
        form = ClasseForm(request.POST, instance=classe)
        if form.is_valid():
            form.save()
            return _render_admin_structure(request, active_tab='classes')
    else:
        form = ClasseForm(instance=classe)

    return render(request, 'core/partials/classe_form.html', {
        'classe_form': form,
        'classe': classe,
        'submit_label': 'Enregistrer',
        'cancel_label': 'Annuler',
        'action_url': reverse('dashboard_admin_edit_classe', args=[classe.id]),
    }, status=400 if request.method == 'POST' else 200)


@role_required('ADMIN')
@require_http_methods(['GET'])
def manage_classe_students_view(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)
    eleves = Utilisateur.objects.filter(classe=classe, role='ELEVE').order_by('email')
    pending_students = Utilisateur.objects.filter(classe__isnull=True, role='ELEVE').order_by('email')
    return render(request, 'core/classe_students_page.html', {
        'classe': classe,
        'eleves': eleves,
        'pending_students': pending_students,
    })

@role_required('ADMIN')
@require_http_methods(['POST'])
def remove_student_from_classe_page_view(request, classe_id, student_id):
    student = get_object_or_404(Utilisateur, pk=student_id)
    student.classe = None
    student.save(update_fields=['classe'])
    return redirect('dashboard_admin_manage_classe_students', classe_id=classe_id)

@role_required('ADMIN')
@require_http_methods(['POST'])
def delete_student_from_classe_page_view(request, classe_id, student_id):
    student = get_object_or_404(Utilisateur, pk=student_id)
    student.delete()
    return redirect('dashboard_admin_manage_classe_students', classe_id=classe_id)

@role_required('ADMIN')
@require_http_methods(['POST'])
def assign_student_to_classe_page_view(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)
    student_id = request.POST.get('student_id')
    if student_id:
        student = get_object_or_404(Utilisateur, pk=student_id)
        student.classe = classe
        student.statut_compte = 'ACTIVE'
        student.is_active = True
        student.save(update_fields=['classe', 'statut_compte', 'is_active'])
    return redirect('dashboard_admin_manage_classe_students', classe_id=classe_id)

@role_required('ADMIN')
@require_http_methods(['POST'])
def add_student_to_classe_page_view(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)
    email = request.POST.get('email')
    password = request.POST.get('password')
    if email and password and not Utilisateur.objects.filter(email=email).exists():
        Utilisateur.objects.create_user(
            email=email,
            password=password,
            role='ELEVE',
            statut_compte='ACTIVE',
            is_active=True,
            classe=classe
        )
    return redirect('dashboard_admin_manage_classe_students', classe_id=classe_id)


@role_required('ADMIN')
@require_http_methods(['GET', 'POST'])
def activate_pending_student_view(request):
    if request.method != 'POST':
        return HttpResponseForbidden('Méthode non autorisée.')

    form = PendingStudentActivationForm(request.POST)
    if form.is_valid():
        student = Utilisateur.objects.get(pk=form.cleaned_data['student_id'])
        student.classe = form.cleaned_data['classe']
        student.statut_compte = 'ACTIVE'
        student.is_active = True
        if student.role == 'ELEVE':
            student.is_formateur = False
        student.save(update_fields=['classe', 'statut_compte', 'is_active', 'is_formateur'])
        return _render_admin_structure(request, active_tab='students')

    return _render_admin_structure(request, {
        'pending_error': form.errors.as_text(),
    }, status=400, active_tab='students')


@role_required('FORMATEUR')
@require_http_methods(['GET', 'POST'])
def create_demande_materiel_view(request):
    if request.method == 'POST':
        form = DemandeMaterielForm(request.POST)
        if form.is_valid():
            demande = form.save(commit=False)
            demande.formateur = request.user
            demande.save()
            return _render_formateur_structure(request)
    else:
        form = DemandeMaterielForm()

    return _render_formateur_structure(request, {'demande_form': form}, status=400 if request.method == 'POST' else 200)


@role_required('ADMIN')
@require_http_methods(['POST'])
def admin_process_demande_view(request, demande_id):
    """Process a DemandeMateriel: approve or reject. Returns refreshed pending demandes section."""
    action = request.POST.get('action')
    demande = get_object_or_404(DemandeMateriel, pk=demande_id)

    if action == 'approve':
        demande.statut = 'APPROVED'
    elif action == 'reject':
        demande.statut = 'REJECTED'
    else:
        return _render_admin_structure(request, {'pending_error': 'Action invalide.'}, status=400, active_tab='logistics')

    demande.save(update_fields=['statut'])
    # After processing, re-render the pending demandes section so HTMX can swap it.
    return render(request, 'core/partials/pending_demandes_section.html', {
        'pending_demandes': DemandeMateriel.objects.filter(statut='PENDING').select_related('formateur', 'equipement', 'atelier_cible').order_by('-date_creation')
    })