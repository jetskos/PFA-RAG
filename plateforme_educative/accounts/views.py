from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.http import HttpResponse
from django.urls import reverse
from .forms import InscriptionForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from .models import Utilisateur


def register_view(request):
    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Connecte automatiquement l'utilisateur après l'inscription
            login(request, user)
            if request.headers.get('HX-Request') == 'true':
                response = HttpResponse(status=204)
                response['HX-Redirect'] = reverse('accounts:login')
                return response
            return redirect('accounts:login')
    else:
        form = InscriptionForm()

    context = {'form': form}
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'accounts/partials/register_form.html', context)
    return render(request, 'accounts/register.html', context)


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
            niveau = request.POST.get('niveau') or 'DEBUTANT'
            is_formateur = request.POST.get('is_formateur') == 'true'

            if not email or not password:
                return JsonResponse({'status': 'error', 'message': 'Email et mot de passe sont requis.'}, status=400)
            if Utilisateur.objects.filter(email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'Cet email existe deja.'}, status=400)
            if role not in dict(Utilisateur.ROLE_CHOICES):
                return JsonResponse({'status': 'error', 'message': 'Role invalide.'}, status=400)
            if niveau not in dict(Utilisateur.NIVEAU_CHOICES):
                return JsonResponse({'status': 'error', 'message': 'Niveau invalide.'}, status=400)

            # Ensure role and helper flag remain coherent.
            if role == 'FORMATEUR':
                is_formateur = True

            user = Utilisateur.objects.create_user(
                email=email,
                password=password,
                role=role,
                niveau=niveau,
                is_formateur=is_formateur,
            )
            return JsonResponse({
                'status': 'success',
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'role': user.role,
                    'niveau': user.niveau,
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
        niveau = request.POST.get('niveau')
        role = request.POST.get('role')

        if role in dict(Utilisateur.ROLE_CHOICES):
            user.role = role
            if role == 'FORMATEUR':
                is_formateur = True

        user.is_formateur = is_formateur
        if niveau in dict(Utilisateur.NIVEAU_CHOICES):
            user.niveau = niveau
        user.save()
        return JsonResponse({'status': 'success'})

    # GET
    users = Utilisateur.objects.all().order_by('-date_creation')
    return render(request, 'accounts/admin_dashboard.html', {
        'users': users,
        'niveau_choices': Utilisateur.NIVEAU_CHOICES,
        'role_choices': Utilisateur.ROLE_CHOICES,
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
            'niveau': user.get_niveau_display(),
            'is_formateur': user.is_formateur,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'date_creation': user.date_creation.strftime('%d/%m/%Y %H:%M'),
            'last_login': user.last_login.strftime('%d/%m/%Y %H:%M') if user.last_login else 'Jamais',
        }
    })