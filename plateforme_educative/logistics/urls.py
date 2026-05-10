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
]
