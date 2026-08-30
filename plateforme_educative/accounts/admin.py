from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Utilisateur, Niveau, Classe, Notification, ConfigurationSysteme


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Filet de sécurité superuser : débloquer / réinitialiser un compte quand
    l'interface `/auth/gestion/` ne suffit pas."""
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'role', 'statut_compte', 'is_active', 'is_staff')
    list_filter = ('role', 'statut_compte', 'is_active', 'is_formateur', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    readonly_fields = ('date_creation', 'last_login')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Identité'), {'fields': ('first_name', 'last_name', 'photo')}),
        (_('Rôle & accès'), {'fields': ('role', 'statut_compte', 'classe', 'is_active',
                                        'is_formateur', 'onboarding_completed')}),
        (_('Mot de passe temporaire'), {'fields': ('is_temp_password', 'temp_password_created_at')}),
        (_('Permissions Django'), {'classes': ('collapse',),
                                   'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Dates'), {'fields': ('last_login', 'date_creation')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',),
                'fields': ('email', 'password1', 'password2', 'role', 'is_active')}),
    )


@admin.register(Niveau)
class NiveauAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'ordre', 'actif')
    list_editable = ('ordre', 'actif')
    search_fields = ('nom', 'code')


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'niveau', 'annee_scolaire')
    list_filter = ('niveau', 'annee_scolaire')
    search_fields = ('nom', 'code')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('destinataire', 'type', 'titre', 'lu', 'date_creation')
    list_filter = ('type', 'lu')
    search_fields = ('titre', 'message', 'destinataire__email')
    readonly_fields = ('date_creation',)


@admin.register(ConfigurationSysteme)
class ConfigurationSystemeAdmin(admin.ModelAdmin):
    list_display = ('id', 'mode_hors_ligne', 'llm_provider', 'activer_hls')

    def has_add_permission(self, request):
        # Singleton (id=1) : pas de création multiple depuis l'admin.
        return not ConfigurationSysteme.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
