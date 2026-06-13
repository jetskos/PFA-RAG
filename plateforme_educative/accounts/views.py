from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.urls import reverse
from .forms import InscriptionForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from .models import Utilisateur, Niveau, Classe
from .forms import ProfileForm
from apprentissage.models import Progression, ChapitreVisite, ChapitreComplete, Cours


def register_view(request):
    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save()
            if request.headers.get('HX-Request') == 'true':
                response = HttpResponse(status=204)
                response['HX-Redirect'] = reverse('accounts:pending')
                return response
            return redirect('accounts:pending')
    else:
        form = InscriptionForm()

    context = {'form': form}
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'accounts/partials/register_form.html', context)
    return render(request, 'accounts/register.html', context)


def pending_view(request):
    return render(request, 'accounts/pending.html')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    """Superuser view to manage users (create/update/delete)."""
    if request.method == 'POST':
        # Support action-based POSTs: save or delete
        action = request.POST.get('action', 'save')

        if action == 'create':
            email = (request.POST.get('email') or '').strip().lower()
            password = request.POST.get('password') or ''
            role = request.POST.get('role') or 'ELEVE'
            classe_id = request.POST.get('classe_id') or None
            niveau_id = request.POST.get('niveau') or None
            is_formateur = request.POST.get('is_formateur') == 'true'

            if not email or not password:
                return JsonResponse({'status': 'error', 'message': 'Email et mot de passe sont requis.'}, status=400)
            if Utilisateur.objects.filter(email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'Cet email existe deja.'}, status=400)
            if role not in dict(Utilisateur.ROLE_CHOICES):
                return JsonResponse({'status': 'error', 'message': 'Role invalide.'}, status=400)

            # Ensure role and helper flag remain coherent.
            if role == 'FORMATEUR':
                is_formateur = True

            classe = None
            if classe_id:
                try:
                    classe = Classe.objects.select_related('niveau').get(pk=classe_id)
                except Classe.DoesNotExist:
                    return JsonResponse({'status': 'error', 'message': 'Classe introuvable.'}, status=404)
            elif niveau_id:
                try:
                    niveau = Niveau.objects.get(pk=niveau_id)
                except Niveau.DoesNotExist:
                    return JsonResponse({'status': 'error', 'message': 'Niveau introuvable.'}, status=404)
                classe = (
                    Classe.objects.filter(niveau=niveau, actif=True)
                    .order_by('annee_scolaire', 'nom')
                    .first()
                )

            statut_compte = 'ACTIVE' if role != 'ELEVE' else 'PENDING'
            is_active = role != 'ELEVE'

            user = Utilisateur.objects.create_user(
                email=email,
                password=password,
                role=role,
                statut_compte=statut_compte,
                is_active=is_active,
                classe=classe,
                is_formateur=is_formateur,
            )
            return JsonResponse({
                'status': 'success',
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'role': user.role,
                    'statut_compte': user.statut_compte,
                    'niveau': user.niveau,
                    'classe': str(user.classe) if user.classe else '',
                    'is_formateur': user.is_formateur,
                    'is_superuser': user.is_superuser,
                }
            })

        user_id = request.POST.get('user_id')

        try:
            user = Utilisateur.objects.get(pk=user_id)
        except Utilisateur.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Utilisateur introuvable'}, status=404)

        if action == 'delete':
            # Prevent deleting oneself or other superusers
            if str(user.pk) == str(request.user.pk):
                return JsonResponse({'status': 'error', 'message': 'Vous ne pouvez pas supprimer votre propre compte.'}, status=400)
            if user.is_superuser:
                return JsonResponse({'status': 'error', 'message': 'Impossible de supprimer un superuser.'}, status=400)
            user.delete()
            return JsonResponse({'status': 'success'})

        # default: save updates
        is_formateur = request.POST.get('is_formateur') == 'true'
        role = request.POST.get('role')
        classe_id = request.POST.get('classe_id') or None
        niveau_id = request.POST.get('niveau') or None

        if role in dict(Utilisateur.ROLE_CHOICES):
            user.role = role
            if role == 'FORMATEUR':
                is_formateur = True

        user.is_formateur = is_formateur

        if classe_id:
            try:
                user.classe = Classe.objects.get(pk=classe_id)
            except Classe.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Classe introuvable'}, status=404)
        elif niveau_id:
            try:
                niveau = Niveau.objects.get(pk=niveau_id)
            except Niveau.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Niveau introuvable'}, status=404)
            user.classe = (
                Classe.objects.filter(niveau=niveau, actif=True)
                .order_by('annee_scolaire', 'nom')
                .first()
            )
        elif role == 'ELEVE' and not user.classe:
            user.statut_compte = 'PENDING'
            user.is_active = False
        elif role != 'ELEVE':
            user.statut_compte = 'ACTIVE'
            user.is_active = True

        user.save()
        return JsonResponse({'status': 'success'})

    # GET
    users = Utilisateur.objects.all().order_by('-date_creation')
    return render(request, 'accounts/admin_dashboard.html', {
        'users': users,
        'role_choices': Utilisateur.ROLE_CHOICES,
        'niveau_choices': [(str(niveau.id), niveau.nom) for niveau in Niveau.objects.order_by('ordre', 'nom')],
        'niveaux': Niveau.objects.prefetch_related('classes').order_by('ordre', 'nom'),
        'classes': Classe.objects.select_related('niveau').order_by('niveau__ordre', 'nom'),
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_details(request, user_id):
    try:
        user = Utilisateur.objects.get(pk=user_id)
    except Utilisateur.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Utilisateur introuvable'}, status=404)

    return JsonResponse({
        'status': 'success',
        'user': {
            'id': str(user.id),
            'email': user.email,
            'role': user.get_role_display(),
            'niveau': user.classe.niveau.nom if user.classe and user.classe.niveau else '',
            'classe': str(user.classe) if user.classe else '',
            'statut_compte': user.get_statut_compte_display(),
            'is_formateur': user.is_formateur,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'date_creation': user.date_creation.strftime('%d/%m/%Y %H:%M'),
            'last_login': user.last_login.strftime('%d/%m/%Y %H:%M') if user.last_login else 'Jamais',
        }
    })


@login_required
def profile_view(request):
    """Affiche le profil de l'utilisateur connecté avec sa progression d'apprentissage."""
    progressions = list(
        Progression.objects.filter(etudiant=request.user)
        .select_related('cours')
        .prefetch_related('chapitres_valides')
        .order_by('-date_derniere_consultation')
    )

    completed_progressions = [progression for progression in progressions if progression.pourcentage == 100]
    active_progressions = [progression for progression in progressions if 0 < progression.pourcentage < 100]

    total_chapitres_valides = sum(progression.chapitres_valides.count() for progression in progressions)
    total_chapitres = sum(progression.cours.chapitres.count() for progression in progressions)

    recent_visits = list(
        ChapitreVisite.objects.filter(etudiant=request.user)
        .select_related('chapitre', 'chapitre__cours')
        .order_by('-date_visite')[:5]
    )
    recent_completions = list(
        ChapitreComplete.objects.filter(etudiant=request.user)
        .select_related('chapitre', 'chapitre__cours')
        .order_by('-date_completion')[:5]
    )

    if request.user.is_superuser:
        role_context = {
            'role_title': 'Profil administrateur',
            'role_description': 'Vue de pilotage du compte administrateur et des accès système.',
            'role_actions': [
                {'label': 'Gérer les utilisateurs', 'url': reverse('accounts:admin_dashboard')},
                {'label': 'Voir l’inventaire', 'url': reverse('logistics:inventaire')},
            ],
            'role_kpis': {
                'courses': Cours.objects.filter(actif=True).count(),
                'created_courses': Cours.objects.filter(createur=request.user).count(),
                'progressions': Progression.objects.count(),
            },
        }
    elif request.user.is_formateur:
        role_context = {
            'role_title': 'Profil formateur',
            'role_description': 'Vue de pilotage des contenus créés et des parcours encadrés.',
            'role_actions': [
                {'label': 'Mon espace formateur', 'url': reverse('apprentissage:espace_formateur')},
                {'label': 'Créer un cours', 'url': reverse('apprentissage:nouveau_cours')},
            ],
            'role_kpis': {
                'courses': Cours.objects.filter(createur=request.user).count(),
                'published_courses': Cours.objects.filter(createur=request.user, actif=True).count(),
                'progressions': Progression.objects.filter(cours__createur=request.user).count(),
            },
        }
    else:
        role_context = {
            'role_title': 'Profil apprenant',
            'role_description': 'Vue personnelle du suivi pédagogique et des chapitres validés.',
            'role_actions': [
                {'label': 'Voir les cours', 'url': reverse('apprentissage:liste_cours')},
            ],
            'role_kpis': {
                'courses': len(progressions),
                'completed': len(completed_progressions),
                'in_progress': len(active_progressions),
            },
        }

    context = {
        'profile_user': request.user,
        'profile_class': request.user.classe,
        'profile_niveau': request.user.classe.niveau if request.user.classe else None,
        'progressions': progressions,
        'completed_progressions': completed_progressions,
        'active_progressions': active_progressions,
        'recent_visits': recent_visits,
        'recent_completions': recent_completions,
        'role_context': role_context,
        'profile_stats': {
            'started': len(progressions),
            'completed': len(completed_progressions),
            'in_progress': len(active_progressions),
            'chapters_validated': total_chapitres_valides,
            'chapters_total': total_chapitres,
        },
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def profile_edit_view(request):
    """Permet à l'utilisateur de mettre à jour son profil de base."""
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'accounts/profile_edit.html', {
        'form': form,
        'profile_user': request.user,
    })