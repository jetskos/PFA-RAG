"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import (
    home_view,
    dashboard_router,
    admin_dashboard_view,
    formateur_dashboard_view,
    student_dashboard_view,
    create_niveau_view,
    create_classe_view,
    edit_classe_view,
    manage_classe_students_view,
    remove_student_from_classe_page_view,
    delete_student_from_classe_page_view,
    assign_student_to_classe_page_view,
    add_student_to_classe_page_view,
    activate_pending_student_view,
    edit_niveau_view,
    create_demande_materiel_view,
    admin_process_demande_view,
)

urlpatterns = [
    path('', home_view, name='accueil'),
    path('dashboard/', dashboard_router, name='dashboard'),
    path('dashboard/admin/', admin_dashboard_view, name='dashboard_admin'),
    path('dashboard/admin/niveaux/creer/', create_niveau_view, name='dashboard_admin_create_niveau'),
    path('dashboard/admin/niveaux/<uuid:niveau_id>/editer/', edit_niveau_view, name='dashboard_admin_edit_niveau'),
    path('dashboard/admin/classes/creer/', create_classe_view, name='dashboard_admin_create_classe'),
    path('dashboard/admin/classes/<uuid:classe_id>/editer/', edit_classe_view, name='dashboard_admin_edit_classe'),
    path('dashboard/admin/classes/<uuid:classe_id>/eleves/', manage_classe_students_view, name='dashboard_admin_manage_classe_students'),
    path('dashboard/admin/classes/<uuid:classe_id>/eleves/<uuid:student_id>/remove/', remove_student_from_classe_page_view, name='dashboard_admin_remove_student_page'),
    path('dashboard/admin/classes/<uuid:classe_id>/eleves/<uuid:student_id>/delete/', delete_student_from_classe_page_view, name='dashboard_admin_delete_student_page'),
    path('dashboard/admin/classes/<uuid:classe_id>/eleves/assign/', assign_student_to_classe_page_view, name='dashboard_admin_assign_student_page'),
    path('dashboard/admin/classes/<uuid:classe_id>/eleves/add/', add_student_to_classe_page_view, name='dashboard_admin_add_student_page'),
    path('dashboard/admin/pending/activer/', activate_pending_student_view, name='dashboard_admin_activate_pending_student'),
        path('dashboard/admin/demandes/<uuid:demande_id>/process/',
            admin_process_demande_view, name='dashboard_admin_process_demande'),
    path('dashboard/formateur/', formateur_dashboard_view, name='dashboard_formateur'),
    path('dashboard/formateur/demandes/creer/', create_demande_materiel_view, name='dashboard_formateur_create_demande'),
    path('dashboard/student/', student_dashboard_view, name='dashboard_student'),
    path('admin/', admin.site.urls),
    path('auth/', include('accounts.urls')),
    path('apprentissage/', include('apprentissage.urls')),
    path('logistics/', include('logistics.urls', namespace='logistics')),
    path('tuteur/', include('tuteur_ia.urls', namespace='tuteur_ia')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
