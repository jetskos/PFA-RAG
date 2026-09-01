from django.contrib import admin
from .models import Cours, Chapitre, Document, SatelliteUpdate


@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = ('titre', 'niveau', 'source', 'actif', 'date_creation')
    list_filter = ('source', 'niveau', 'actif', 'date_creation')
    search_fields = ('titre', 'description')
    fieldsets = (
        ('Informations générales', {
            'fields': ('titre', 'description', 'resume', 'niveau')
        }),
        ('Statut', {
            'fields': ('actif', 'source'),
            'description': "« satellite » = remplacé à chaque mise à jour ; « manuel » = persistant.",
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


@admin.register(SatelliteUpdate)
class SatelliteUpdateAdmin(admin.ModelAdmin):
    list_display = ('logical_name', 'titre_cours', 'status', 'size', 'cycle_id', 'detected_at', 'applied_at')
    list_filter = ('status', 'detected_at')
    search_fields = ('logical_name', 'titre_cours', 'file_hash')
    readonly_fields = ('id', 'file_hash', 'detected_at', 'applied_at', 'import_job', 'applied_by')
    ordering = ('-detected_at',)


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
