from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view
from .views import (
    MeView,
    CustomObtainAuthToken,
    CoursViewSet,
    ChapitreViewSet,
    DocumentViewSet,
    ProgressionViewSet,
    SessionQCMViewSet,
    api_docs_view
)

router = DefaultRouter()
router.register('cours', CoursViewSet, basename='cours')
router.register('chapitres', ChapitreViewSet, basename='chapitres')
router.register('documents', DocumentViewSet, basename='documents')
router.register('progressions', ProgressionViewSet, basename='progressions')
router.register('sessions-qcm', SessionQCMViewSet, basename='sessions-qcm')

app_name = 'api'

urlpatterns = [
    path('', include(router.urls)),
    path('me/', MeView.as_view(), name='me'),
    path('login/', CustomObtainAuthToken.as_view(), name='login'),
    path('docs/', api_docs_view, name='docs'),
    path('schema/', get_schema_view(
        title="Plateforme Éducative API",
        description="Documentation de l'API de la plateforme éducative.",
        version="1.0.0"
    ), name='openapi-schema'),
]
