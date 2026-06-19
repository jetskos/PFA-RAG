from rest_framework import serializers
from apprentissage.models import Cours, Chapitre, Document, Progression
from tuteur_ia.models import SessionQCM
from accounts.models import Utilisateur

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = Utilisateur
        fields = ('id', 'email', 'role', 'classe', 'is_formateur')
        read_only_fields = ('id', 'email', 'role', 'classe', 'is_formateur')

class CoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cours
        fields = ('id', 'titre', 'description', 'niveau', 'resume', 'date_creation', 'date_modification', 'actif', 'createur')
        read_only_fields = ('id', 'date_creation', 'date_modification', 'createur')

class ChapitreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapitre
        fields = ('id', 'cours', 'titre', 'description', 'ordre', 'url_video', 'date_creation', 'actif')
        read_only_fields = ('id', 'date_creation')

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ('id', 'chapitre', 'titre', 'type_document', 'fichier_pdf', 'description', 'ordre', 'actif')

class ProgressionSerializer(serializers.ModelSerializer):
    pourcentage = serializers.ReadOnlyField()

    class Meta:
        model = Progression
        fields = ('id', 'etudiant', 'cours', 'chapitres_valides', 'pourcentage', 'date_derniere_consultation')
        read_only_fields = ('id', 'etudiant', 'pourcentage', 'date_derniere_consultation')

class SessionQCMSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionQCM
        fields = ('id', 'etudiant', 'chapitre', 'questions', 'reponses', 'score', 'statut', 'tentative', 'date_creation', 'date_modification')
        read_only_fields = ('id', 'etudiant', 'questions', 'score', 'statut', 'tentative', 'date_creation', 'date_modification')
