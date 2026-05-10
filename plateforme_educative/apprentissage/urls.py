from django.urls import path
from . import views

app_name = 'apprentissage'

urlpatterns = [
    path('', views.liste_cours, name='liste_cours'),
    path('formateur/', views.espace_formateur, name='espace_formateur'),
    path('formateur/cours/nouveau/', views.nouveau_cours, name='nouveau_cours'),
    path('formateur/cours/<uuid:pk>/', views.gerer_cours, name='gerer_cours'),
    path('formateur/cours/<uuid:pk>/editer/', views.editer_cours, name='editer_cours'),
    path('formateur/cours/<uuid:pk>/supprimer/', views.supprimer_cours, name='supprimer_cours'),
    path('formateur/cours/<uuid:cours_id>/chapitre/ajouter/', views.ajouter_chapitre, name='ajouter_chapitre'),
    path('formateur/chapitre/<uuid:chapitre_id>/', views.gerer_chapitre, name='gerer_chapitre'),
    path('formateur/chapitre/<uuid:chapitre_id>/editer/', views.editer_chapitre, name='editer_chapitre'),
    path('formateur/chapitre/<uuid:chapitre_id>/supprimer/', views.supprimer_chapitre, name='supprimer_chapitre'),
    path('formateur/chapitre/<uuid:chapitre_id>/document/ajouter/', views.ajouter_document, name='ajouter_document'),
    path('formateur/document/<uuid:document_id>/editer/', views.editer_document, name='editer_document'),
    path('formateur/document/<uuid:document_id>/supprimer/', views.supprimer_document, name='supprimer_document'),
    path('cours/<uuid:cours_id>/', views.detail_cours, name='detail_cours'),
    path('cours/<uuid:cours_id>/chapitre/<uuid:chapitre_id>/', views.detail_chapitre, name='detail_chapitre'),
    path('document/<uuid:document_id>/telecharger/', views.telecharger_document, name='telecharger_document'),
    path('chapitre/<uuid:chapitre_id>/valider/', views.valider_chapitre, name='valider_chapitre'),
]
