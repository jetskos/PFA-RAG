from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('', views.audit_log_view, name='audit_log'),
    path('export/', views.export_audit_csv, name='export_audit_csv'),
]
