from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # ── Vues Formateur ────────────────────────────────────────────────────────
    path('cours/<uuid:cours_id>/', views.formateur_course_analytics, name='formateur_course_analytics'),
    path('cours/<uuid:cours_id>/export/', views.export_formateur_analytics_csv, name='export_formateur_analytics_csv'),

    # ── Vues Admin ────────────────────────────────────────────────────────────
    path('admin/', views.admin_dashboard_analytics, name='admin_dashboard_analytics'),
    path('admin/export/', views.export_admin_analytics_csv, name='export_admin_analytics_csv'),
]
