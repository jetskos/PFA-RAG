from django.urls import path
from . import views

app_name = 'apprentissage'

urlpatterns = [
    path('', views.liste_cours, name='liste_cours'),
    path('cours/<uuid:cours_id>/', views.detail_cours, name='detail_cours'),
    path('cours/<uuid:cours_id>/chapitre/<uuid:chapitre_id>/', views.detail_chapitre, name='detail_chapitre'),
    path('document/<uuid:document_id>/telecharger/', views.telecharger_document, name='telecharger_document'),
]
