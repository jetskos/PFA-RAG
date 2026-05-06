from django.contrib import admin
from .models import Cours, Chapitre, Document


@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = ('titre', 'niveau', 'actif', 'date_creation')
    list_filter = ('niveau', 'actif', 'date_creation')
    search_fields = ('titre', 'description')
    fieldsets = (
        ('Informations générales', {
            'fields': ('titre', 'description', 'resume', 'niveau')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('date_creation', 'date_modification')


@admin.register(Chapitre)
class ChapitreAdmin(admin.ModelAdmin):
    list_display = ('titre', 'cours', 'ordre', 'actif')
    list_filter = ('cours', 'actif', 'date_creation')
    search_fields = ('titre', 'description')
    ordering = ('cours', 'ordre')
    fieldsets = (
        ('Informations générales', {
            'fields': ('cours', 'titre', 'description', 'ordre')
        }),
        ('Contenu pédagogique', {
            'fields': ('url_video',)
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('date_creation',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('titre', 'chapitre', 'type_document', 'actif', 'date_creation')
    list_filter = ('type_document', 'actif', 'date_creation', 'chapitre__cours')
    search_fields = ('titre', 'description', 'contenu_extrait')
    ordering = ('chapitre', 'type_document', 'ordre')
    fieldsets = (
        ('Informations générales', {
            'fields': ('chapitre', 'titre', 'type_document', 'description')
        }),
        ('Fichier PDF', {
            'fields': ('fichier_pdf',)
        }),
        ('Contenu extrait (IA)', {
            'fields': ('contenu_extrait',),
            'classes': ('collapse',),
            'description': 'Rempli automatiquement lors de l\'upload du PDF'
        }),
        ('Affichage', {
            'fields': ('ordre', 'actif')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('date_creation', 'date_modification', 'contenu_extrait')
