from django.urls import path
from . import views

app_name = 'logistics'

urlpatterns = [
    path('', views.inventaire_view, name='inventaire'),
    path('tickets/', views.tickets_view, name='tickets'),
    path('ticket/nuevo/', views.nuevo_ticket, name='nuevo_ticket'),
    path('equipement/ajouter/', views.ajouter_equipement, name='ajouter_equipement'),
    path('equipement/<int:pk>/editer/', views.editer_equipement, name='editer_equipement'),
    path('equipement/<int:pk>/supprimer/', views.supprimer_equipement, name='supprimer_equipement'),

    # Ateliers
    path('ateliers/', views.ateliers_view, name='ateliers'),
    path('atelier/ajouter/', views.ajouter_atelier, name='ajouter_atelier'),
    path('atelier/<int:pk>/editer/', views.editer_atelier, name='editer_atelier'),
    path('atelier/<int:pk>/supprimer/', views.supprimer_atelier, name='supprimer_atelier'),

    # Demandes
    path('demandes/', views.demandes_view, name='demandes'),
    path('demande/ajouter/', views.ajouter_demande, name='ajouter_demande'),
    path('demande/<int:pk>/editer/', views.editer_demande, name='editer_demande'),
    path('demande/<int:pk>/supprimer/', views.supprimer_demande, name='supprimer_demande'),
    path('demande/<int:pk>/statut/', views.changer_statut_demande, name='changer_statut_demande'),
]
