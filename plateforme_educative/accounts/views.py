from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.urls import reverse
from .forms import InscriptionForm, ProfileForm, PasswordResetRequestForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from .models import Utilisateur, Niveau, Classe, Notification
from apprentissage.models import Progression, ChapitreVisite, ChapitreComplete, Cours
import secrets
import string
from django.utils import timezone
from datetime import timedelta
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView


def register_view(request):
    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save()
            if user.role == 'ELEVE':
                from django.db.models import Q
                from accounts.notifications import notifier
                admins = Utilisateur.objects.filter(Q(role='ADMIN') | Q(is_superuser=True))
                for admin in admins:
                    notifier(
                        destinataire=admin,
                        type='NOUVELLE_INSCRIPTION',
                        titre="Nouvelle inscription d'élève",
                        message=f"L'étudiant {user.get_full_name()} s'est inscrit et attend d'être associé à une classe.",
                        url=reverse('dashboard_admin') + '?tab=students',
                        envoyer_email=False
                    )
            if request.headers.get('HX-Request') == 'true':
                response = HttpResponse(status=204)
                response['HX-Redirect'] = reverse('accounts:pending')
                return response
            return redirect('accounts:pending')
    else:
        form = InscriptionForm()

    context = {'form': form}
    if request.headers.get('HX-Request') == 'true' and request.method == 'POST':
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
            is_formateur = (role == 'FORMATEUR')

            first_name = (request.POST.get('first_name') or '').strip()
            last_name = (request.POST.get('last_name') or '').strip()

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
                first_name=first_name,
                last_name=last_name,
                role=role,
                statut_compte=statut_compte,
                is_active=is_active,
                classe=classe,
                is_formateur=is_formateur,
            )

            if role == 'ADMIN':
                user.is_staff = True
                user.is_superuser = True
                user.save()
            return JsonResponse({
                'status': 'success',
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'full_name': user.get_full_name(),
                    'role': user.role,
                    'statut_compte': user.statut_compte,
                    'niveau': user.niveau,
                    'classe': str(user.classe) if user.classe else '',
                    'is_formateur': user.is_formateur,
                    'is_superuser': user.is_superuser,
                    'photo_url': user.photo.url if user.photo else '',
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
        role = request.POST.get('role')
        classe_id = request.POST.get('classe_id') or None
        niveau_id = request.POST.get('niveau') or None

        if role in dict(Utilisateur.ROLE_CHOICES):
            user.role = role
            user.is_formateur = (role == 'FORMATEUR')
            if role == 'ADMIN':
                user.is_staff = True
                user.is_superuser = True
            else:
                user.is_staff = False
                user.is_superuser = False

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

        # --- Email de bienvenue si le compte passe à ACTIF ---
        if user.is_active and user.statut_compte == 'ACTIVE' and user.role == 'ELEVE':
            try:
                from django.core.mail import EmailMultiAlternatives
                from django.template.loader import render_to_string
                from django.utils.html import strip_tags
                from accounts.tasks import envoyer_email_task
                ctx = {
                    'user': user,
                    'base_url': getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
                }
                html_content = render_to_string('accounts/emails/activation_email.html', ctx)
                text_content = strip_tags(html_content)
                envoyer_email_task.delay(
                    subject="Votre compte EduTech est activé !",
                    text_content=text_content,
                    html_content=html_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to_list=[user.email],
                )
            except Exception:
                pass

        user.save()
        return JsonResponse({'status': 'success'})

    # GET
    users_list = Utilisateur.objects.all().order_by('-date_creation')
    total_users = users_list.count()
    student_count = users_list.filter(role='ELEVE').count()
    formateur_count = users_list.filter(role='FORMATEUR').count()
    admin_count = users_list.filter(role='ADMIN').count()

    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/admin_dashboard.html', {
        'users': page_obj,
        'page_obj': page_obj,
        'role_choices': Utilisateur.ROLE_CHOICES,
        'niveau_choices': [(str(niveau.id), niveau.nom) for niveau in Niveau.objects.order_by('ordre', 'nom')],
        'niveaux': Niveau.objects.prefetch_related('classes').order_by('ordre', 'nom'),
        'classes': Classe.objects.select_related('niveau').order_by('niveau__ordre', 'nom'),
        'total_users': total_users,
        'student_count': student_count,
        'formateur_count': formateur_count,
        'admin_count': admin_count,
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
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'full_name': user.get_full_name(),
            'role': user.get_role_display(),
            'role_code': user.role,
            'niveau': user.classe.niveau.nom if user.classe and user.classe.niveau else '',
            'classe': str(user.classe) if user.classe else '',
            'statut_compte': user.get_statut_compte_display(),
            'is_formateur': user.is_formateur,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'photo_url': user.photo.url if user.photo else '',
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
@transaction.atomic
def profile_edit_view(request):
    """Met a jour le profil : email + photo (upload / suppression)."""
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            # Suppression explicite de l'avatar si la case est cochee
            if form.cleaned_data.get('supprimer_photo') and request.user.photo:
                request.user.photo.delete(save=False)  # efface le fichier disque
                form.instance.photo = None
            form.save()
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'accounts/profile_edit.html', {
        'form': form,
        'profile_user': request.user,
    })


@login_required
def notifications_list_view(request):
    """Affiche la liste des notifications de l'utilisateur."""
    notifications = request.user.notifications.all()
    return render(request, 'accounts/notifications.html', {
        'notifications': notifications
    })


@login_required
@require_http_methods(['POST'])
def mark_notification_read_view(request, pk):
    """Marque une notification spécifique comme lue."""
    notification = get_object_or_404(request.user.notifications, pk=pk)
    notification.lu = True
    notification.save(update_fields=['lu'])
    
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse('', status=200)
        response['HX-Trigger'] = 'update-notifications'
        return response
    return redirect('accounts:notifications_list')


@login_required
def read_and_redirect_notification_view(request, pk):
    """Marque une notification comme lue et redirige vers son URL."""
    notification = get_object_or_404(request.user.notifications, pk=pk)
    notification.lu = True
    notification.save(update_fields=['lu'])
    target_url = notification.url if notification.url else reverse('accounts:notifications_list')
    return redirect(target_url)


@login_required
@require_http_methods(['POST'])
def delete_notification_view(request, pk):
    """Supprime une notification de l'utilisateur."""
    notification = get_object_or_404(request.user.notifications, pk=pk)
    notification.delete()
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse('', status=200)
        response['HX-Trigger'] = 'update-notifications'
        return response
    return redirect('accounts:notifications_list')


@login_required
def unread_notifications_count_view(request):
    """Retourne le HTML du badge notifications non lues (pour polling HTMX)."""
    count = request.user.notifications.filter(lu=False).count()
    if count > 0:
        return HttpResponse(
            f'<span class="notifications-badge" style="position:absolute;top:-2px;right:-2px;background:#ef4444;'
            f'color:white;font-size:9px;font-weight:bold;border-radius:50%;width:16px;height:16px;'
            f'display:flex;align-items:center;justify-content:center;">{count}</span>'
        )
    return HttpResponse('')


@login_required
@require_http_methods(['POST'])
def mark_notifications_read_all_view(request):
    """Marque toutes les notifications de l'utilisateur comme lues."""
    request.user.notifications.filter(lu=False).update(lu=True)
    
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse('', status=200)
        response['HX-Trigger'] = 'update-notifications'
        return response
    return redirect('accounts:notifications_list')


def custom_password_reset_view(request):
    """
    Vue personnalisée pour générer et envoyer un mot de passe temporaire
    valide 10 minutes à l'utilisateur.
    """
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            users = Utilisateur.objects.filter(email__iexact=email, is_active=True)
            for user in users:
                # Génération d'un mot de passe temporaire aléatoire de 8 caractères
                chars = string.ascii_letters + string.digits
                temp_pass = ''.join(secrets.choice(chars) for _ in range(8))

                # Mise à jour de l'utilisateur
                user.set_password(temp_pass)
                user.is_temp_password = True
                user.temp_password_created_at = timezone.now()
                user.save()

                # Envoi du mail (asynchrone via Celery)
                subject = "Votre mot de passe temporaire - EduTech"
                context = {
                    'user': user,
                    'temp_pass': temp_pass,
                    'base_url': getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
                }
                html_content = render_to_string('accounts/emails/temp_password_email.html', context)
                text_content = strip_tags(html_content)

                from accounts.tasks import envoyer_email_task
                envoyer_email_task.delay(
                    subject=subject,
                    text_content=text_content,
                    html_content=html_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to_list=[user.email],
                )

            return redirect('accounts:password_reset_done')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'accounts/password_reset_form.html', {'form': form})



class CustomLoginView(LoginView):
    """
    LoginView personnalisée vérifiant si l'utilisateur se connecte
    avec un mot de passe temporaire expiré (10 minutes).
    """
    template_name = 'accounts/login.html'
    
    def form_valid(self, form):
        user = form.get_user()

        if user.is_temp_password:  # noqa: SIM102
            # Vérification de l'expiration des 10 heures
            if not user.temp_password_created_at or timezone.now() - user.temp_password_created_at > timedelta(hours=10):
                form.add_error(None, "Ce mot de passe temporaire a expiré (validité de 10 heures). L'administrateur doit en générer un nouveau.")
                return self.form_invalid(form)
            else:
                # Connexion de l'utilisateur
                login(self.request, user)
                # Notification de sécurité
                messages.warning(self.request, "Vous êtes connecté avec un mot de passe temporaire. Veuillez le modifier ci-dessous.")
                return redirect('accounts:change_password')
                
        return super().form_valid(form)

    def get_success_url(self):
        user = self.request.user
        # Onboarding prioritaire pour FORMATEUR et ELEVE
        if user.role in ('FORMATEUR', 'ELEVE') and not user.onboarding_completed:
            from django.urls import reverse
            return reverse('accounts:onboarding')
        if user.role == 'FORMATEUR':
            from django.urls import reverse
            return reverse('dashboard_formateur')
        elif user.role == 'ELEVE':
            from django.urls import reverse
            return reverse('dashboard_student')
        return super().get_success_url()


@login_required
def change_password_view(request):
    """
    Vue permettant à l'utilisateur de modifier son mot de passe
    depuis l'onglet Sécurité de son profil.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Nettoyer les drapeaux temporaires
            user.is_temp_password = False
            user.temp_password_created_at = None
            user.save()
            
            # Maintenir la session après changement
            update_session_auth_hash(request, user)
            messages.success(request, "Votre mot de passe a été mis à jour avec succès.")
            return redirect('accounts:profile')
    else:
        form = PasswordChangeForm(request.user)
        
    return render(request, 'accounts/change_password.html', {
        'form': form,
        'profile_user': request.user,
    })

ONBOARDING_STEPS = {
    'FORMATEUR': [
        {'id': 'welcome',    'title': 'Bienvenue sur EduTech !',          'skippable': False},
        {'id': 'profil',     'title': 'Votre profil formateur',           'skippable': False},
        {'id': 'cours',      'title': 'Créez votre premier cours',        'skippable': True},
        {'id': 'logistique', 'title': 'Découvrez la logistique',          'skippable': False},
    ],
    'ELEVE': [
        {'id': 'welcome', 'title': 'Bienvenue sur EduTech !',      'skippable': False},
        {'id': 'profil',  'title': 'Complétez votre profil',       'skippable': False},
        {'id': 'explorer','title': 'Explorez les cours',           'skippable': False},
    ],
}


def _onboarding_dashboard(user):
    if user.role == 'FORMATEUR':
        return reverse('dashboard_formateur')
    return reverse('dashboard_student')


@login_required
def onboarding_view(request):
    user = request.user

    # Seuls FORMATEUR et ELEVE ont un onboarding
    if user.role not in ('FORMATEUR', 'ELEVE'):
        return redirect('dashboard')

    # Déjà complété → dashboard
    if user.onboarding_completed:
        return redirect(_onboarding_dashboard(user))

    steps = ONBOARDING_STEPS[user.role]
    total = len(steps)

    try:
        step_num = int(request.GET.get('step', 1))
    except (ValueError, TypeError):
        step_num = 1
    step_num = max(1, min(step_num, total))
    step = steps[step_num - 1]
    is_htmx = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        # Étape profil — sauvegarde
        if step['id'] == 'profil':
            first_name = request.POST.get('first_name', '').strip()
            last_name  = request.POST.get('last_name', '').strip()
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            if 'photo' in request.FILES:
                user.photo = request.FILES['photo']
            user.save()

        # Dernière étape → compléter l'onboarding
        if step_num == total:
            user.onboarding_completed = True
            user.save()
            if is_htmx:
                response = HttpResponse(status=204)
                response['HX-Redirect'] = _onboarding_dashboard(user)
                return response
            return redirect(_onboarding_dashboard(user))

        # Passer à l'étape suivante
        next_step = step_num + 1
        if is_htmx:
            next_step_data = steps[next_step - 1]
            ctx = {
                'step': next_step_data,
                'step_num': next_step,
                'total': total,
                'steps': steps,
                'niveaux': Niveau.objects.filter(actif=True).order_by('ordre'),
            }
            return render(request, 'accounts/partials/onboarding_step.html', ctx)
        return redirect(f"{reverse('accounts:onboarding')}?step={next_step}")

    # GET
    ctx = {
        'step': step,
        'step_num': step_num,
        'total': total,
        'steps': steps,
        'niveaux': Niveau.objects.filter(actif=True).order_by('ordre'),
    }
    if is_htmx:
        return render(request, 'accounts/partials/onboarding_step.html', ctx)
    return render(request, 'accounts/onboarding.html', ctx)