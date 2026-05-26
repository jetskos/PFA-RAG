from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profil/', views.profile_view, name='profile'),
    path('profil/modifier/', views.profile_edit_view, name='profile_edit'),
    path('gestion/', views.admin_dashboard, name='admin_dashboard'),
    path('gestion/utilisateurs/<uuid:user_id>/details/', views.user_details, name='user_details'),
]