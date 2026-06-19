from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from django.shortcuts import render, get_object_or_404
from django.db.models import Q

from apprentissage.models import Cours, Chapitre, Document, Progression
from tuteur_ia.models import SessionQCM
from accounts.models import Utilisateur
from .serializers import (
    UserSerializer,
    CoursSerializer,
    ChapitreSerializer,
    DocumentSerializer,
    ProgressionSerializer,
    SessionQCMSerializer
)
from .permissions import IsCreateurOrReadOnly

class MeView(APIView):
    """
    Endpoint /api/me/ renvoyant les informations de l'utilisateur connecté.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class CustomObtainAuthToken(ObtainAuthToken):
    """
    Endpoint de login renvoyant le token et des infos utilisateur de base.
    """
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email,
            'full_name': user.get_full_name(),
            'role': user.role
        })
class CoursViewSet(viewsets.ModelViewSet):
    queryset = Cours.objects.all()
    serializer_class = CoursSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreateurOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == 'ADMIN':
            return Cours.objects.all().select_related('niveau', 'createur')
        elif user.is_formateur:
            return Cours.objects.all().select_related('niveau', 'createur')
        else:
            # Élève
            classe = getattr(user, 'classe', None)
            niveau = getattr(classe, 'niveau', None) if classe else None
            if niveau:
                return Cours.objects.filter(niveau=niveau, actif=True).select_related('niveau', 'createur')
            return Cours.objects.none()

    def perform_create(self, serializer):
        serializer.save(createur=self.request.user)

class ChapitreViewSet(viewsets.ModelViewSet):
    queryset = Chapitre.objects.all()
    serializer_class = ChapitreSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreateurOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == 'ADMIN':
            return Chapitre.objects.all().select_related('cours')
        elif user.is_formateur:
            return Chapitre.objects.all().select_related('cours')
        else:
            # Élève
            classe = getattr(user, 'classe', None)
            niveau = getattr(classe, 'niveau', None) if classe else None
            if niveau:
                return Chapitre.objects.filter(
                    cours__niveau=niveau,
                    cours__actif=True,
                    actif=True
                ).select_related('cours')
            return Chapitre.objects.none()

class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == 'ADMIN' or user.is_formateur:
            return Document.objects.all().select_related('chapitre')
        else:
            # Élève
            classe = getattr(user, 'classe', None)
            niveau = getattr(classe, 'niveau', None) if classe else None
            if niveau:
                return Document.objects.filter(
                    chapitre__cours__niveau=niveau,
                    chapitre__cours__actif=True,
                    chapitre__actif=True,
                    actif=True
                ).select_related('chapitre')
            return Document.objects.none()

class ProgressionViewSet(viewsets.ModelViewSet):
    queryset = Progression.objects.all()
    serializer_class = ProgressionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == 'ADMIN' or user.is_formateur:
            return Progression.objects.all().select_related('etudiant', 'cours')
        else:
            return Progression.objects.filter(etudiant=user).select_related('etudiant', 'cours')

    def perform_create(self, serializer):
        serializer.save(etudiant=self.request.user)

class SessionQCMViewSet(viewsets.ModelViewSet):
    queryset = SessionQCM.objects.all()
    serializer_class = SessionQCMSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == 'ADMIN' or user.is_formateur:
            return SessionQCM.objects.all().select_related('etudiant', 'chapitre')
        else:
            return SessionQCM.objects.filter(etudiant=user).select_related('etudiant', 'chapitre')

    def perform_create(self, serializer):
        serializer.save(etudiant=self.request.user)


def api_docs_view(request):
    """
    Rend la page HTML de Swagger UI pour la documentation interactive de l'API.
    """
    return render(request, 'api/docs.html')
