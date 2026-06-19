from django.urls import path
from . import views, views_qcm

app_name = 'tuteur_ia'

urlpatterns = [
    # ── Tuteur IA (chatbot) ──────────────────────────────────────────────
    path('session/<uuid:chapitre_id>/',           views.demarrer_session, name='demarrer_session'),
    path('session/<uuid:session_id>/repondre/',   views.repondre,         name='repondre'),
    path('session/<uuid:session_id>/statut/',     views.statut_session,   name='statut_session'),

    # ── Assistant RAG (explicatif) ───────────────────────────────────────
    path('assistant/<uuid:chapitre_id>/',         views.demarrer_assistant, name='demarrer_assistant'),
    path('assistant/<uuid:session_id>/question/', views.poser_question,     name='poser_question'),


    # ── QCM IA ───────────────────────────────────────────────────────────
    path('qcm/<uuid:chapitre_id>/',               views_qcm.demarrer_qcm,      name='demarrer_qcm'),
    path('qcm/<uuid:chapitre_id>/generer-api/',   views_qcm.generer_qcm_api,   name='generer_qcm_api'),
    path('qcm/<uuid:session_id>/corriger/',       views_qcm.corriger_qcm,      name='corriger_qcm'),
    path('qcm/<uuid:session_id>/resultats/',      views_qcm.resultats_qcm,     name='resultats_qcm'),
    path('qcm/statut/<str:task_id>/',             views_qcm.verifier_statut_qcm, name='verifier_statut_qcm'),

    # ── Profil IA ────────────────────────────────────────────────────────
    path('profil/', views.profil_etudiant_ia, name='profil_ia'),
]

