from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from django.views.decorators.cache import never_cache
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('pending/', views.pending_view, name='pending'),
    path('login/', never_cache(views.CustomLoginView.as_view(
        redirect_authenticated_user=True,   # déjà connecté -> redirige au lieu de réafficher le form
    )), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profil/', views.profile_view, name='profile'),
    path('profil/modifier/', views.profile_edit_view, name='profile_edit'),
    path('profil/securite/', views.change_password_view, name='change_password'),
    path('gestion/', views.admin_dashboard, name='admin_dashboard'),
    path('gestion/utilisateurs/ajouter/', views.ajouter_utilisateur, name='ajouter_utilisateur'),
    path('gestion/utilisateurs/<uuid:user_id>/editer/', views.editer_utilisateur, name='editer_utilisateur'),
    path('gestion/utilisateurs/<uuid:user_id>/supprimer/', views.supprimer_utilisateur, name='supprimer_utilisateur'),
    path('gestion/utilisateurs/export/', views.export_users_excel, name='export_users_excel'),
    path('gestion/utilisateurs/<uuid:user_id>/details/', views.user_details, name='user_details'),
    path('gestion/parametres/', views.system_settings_view, name='system_settings'),
    path('gestion/utilisateurs/reset-password/', views.reset_user_password_ajax, name='reset_user_password_ajax'),
    # Réinitialisation de mot de passe (via mot de passe temporaire)
    path('password-reset/', views.custom_password_reset_view, name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html'
    ), name='password_reset_done'),

    # Notifications
    path('notifications/', views.notifications_list_view, name='notifications_list'),
    path('notifications/unread-count/', views.unread_notifications_count_view, name='unread_notifications_count'),
    path('notifications/marquer-lu/', views.mark_notifications_read_all_view, name='mark_notifications_read_all'),
    path('notifications/<uuid:pk>/marquer-lu/', views.mark_notification_read_view, name='mark_notification_read'),
    path('notifications/<uuid:pk>/lire/', views.read_and_redirect_notification_view, name='read_and_redirect_notification'),
    path('notifications/<uuid:pk>/supprimer/', views.delete_notification_view, name='delete_notification'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
]