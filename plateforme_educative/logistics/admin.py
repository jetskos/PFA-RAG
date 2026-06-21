from django.contrib import admin
from .models import Equipment, Workshop, Ticket


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('nom', 'reference', 'stock_disponible', 'stock_total', 'est_actif')
    list_filter = ('est_actif',)
    search_fields = ('nom', 'reference')
    list_per_page = 25


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display = ('titre', 'date_debut', 'date_fin', 'salle', 'tuteur')
    list_filter = ('salle',)
    search_fields = ('titre', 'salle', 'tuteur__email')
    date_hierarchy = 'date_debut'


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('titre', 'statut', 'equipement', 'atelier', 'ouvert_par')
    list_filter = ('statut', 'equipement')
    search_fields = ('titre', 'description', 'ouvert_par__email')
    list_per_page = 30
