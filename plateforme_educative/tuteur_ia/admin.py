from django.contrib import admin
from .models import ProfilEtudiantIA, SessionTuteur


@admin.register(ProfilEtudiantIA)
class ProfilEtudiantIAAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'style_prefere', 'date_modification')
    list_filter = ('date_modification', 'style_prefere')
    search_fields = ('etudiant__email',)
    readonly_fields = ('date_modification',)
    
    fieldsets = (
        ('Étudiant', {
            'fields': ('etudiant',)
        }),
        ('Profil Pédagogique', {
            'fields': ('concepts_maitrises', 'concepts_fragiles', 'erreurs_communes', 'style_prefere')
        }),
        ('Métadonnées', {
            'fields': ('date_modification',),
            'classes': ('collapse',)
        }),
    )


@admin.register(SessionTuteur)
class SessionTuteurAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'chapitre', 'statut', 'mastery_score_final', 'date_creation')
    list_filter = ('statut', 'date_creation', 'chapitre__cours')
    search_fields = ('etudiant__email', 'chapitre__titre')
    readonly_fields = ('id', 'thread_id', 'date_creation', 'date_modification')
    
    fieldsets = (
        ('Informations Session', {
            'fields': ('id', 'thread_id', 'etudiant', 'chapitre')
        }),
        ('Statut et Résultats', {
            'fields': ('statut', 'mastery_score_final')
        }),
        ('Métadonnées', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Les sessions sont créées automatiquement via les vues
        return False
