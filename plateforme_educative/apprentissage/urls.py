from django.urls import path
from . import views

app_name = 'apprentissage'

urlpatterns = [
    # ── Cours publics ─────────────────────────────────────────────────────────
    path('', views.liste_cours, name='liste_cours'),
    path('cours/<uuid:cours_id>/', views.detail_cours, name='detail_cours'),
    path('cours/<uuid:cours_id>/chapitre/<uuid:chapitre_id>/', views.detail_chapitre, name='detail_chapitre'),
    path('document/<uuid:document_id>/telecharger/', views.telecharger_document, name='telecharger_document'),
    path('chapitre/<uuid:chapitre_id>/valider/', views.valider_chapitre, name='valider_chapitre'),

    # ── Espace formateur ──────────────────────────────────────────────────────
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

    # ── Notes (Formateur) ─────────────────────────────────────────────────────
    path('formateur/notes/', views.formateur_notes_view, name='formateur_notes'),
    path('formateur/notes/export/', views.exporter_notes_classe_csv, name='exporter_notes_classe_csv'),

    # ── Devoirs (Formateur) ───────────────────────────────────────────────────
    path('formateur/chapitre/<uuid:chapitre_id>/devoir/creer/', views.devoir_creer_view, name='devoir_creer'),
    path('formateur/devoir/<uuid:devoir_id>/editer/', views.devoir_editer_view, name='devoir_editer'),
    path('formateur/devoir/<uuid:devoir_id>/supprimer/', views.devoir_supprimer_view, name='devoir_supprimer'),
    path('formateur/soumission/<uuid:soumission_id>/noter/', views.soumission_noter_view, name='soumission_noter'),

    # ── Carnet de notes (Élève) ───────────────────────────────────────────────
    path('notes/', views.mes_notes_view, name='mes_notes'),
    path('notes/export/', views.exporter_bulletin_csv, name='exporter_bulletin_csv'),

    # ── Devoirs (Élève) ───────────────────────────────────────────────────────
    path('devoirs/', views.devoirs_liste_view, name='devoirs_liste'),
    path('devoirs/<uuid:devoir_id>/', views.devoir_detail_view, name='devoir_detail'),

    # ── Calendrier et Événements ──────────────────────────────────────────────
    path('calendrier/', views.calendrier_view, name='calendrier'),
    path('calendrier/creer/', views.creer_evenement, name='creer_evenement'),
    path('calendrier/<uuid:pk>/modifier/', views.modifier_evenement, name='modifier_evenement'),
    path('calendrier/<uuid:pk>/supprimer/', views.supprimer_evenement, name='supprimer_evenement'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('formateur/analytics/', views.formateur_analytics_dashboard, name='formateur_analytics'),
    path('formateur/analytics/data/', views.formateur_analytics_data, name='formateur_analytics_data'),
    path('admin/analytics/', views.admin_analytics_dashboard, name='admin_analytics'),
    path('admin/analytics/data/', views.admin_analytics_data, name='admin_analytics_data'),
]
