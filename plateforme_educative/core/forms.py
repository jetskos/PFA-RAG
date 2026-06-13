from django import forms
from django.contrib.auth import get_user_model

from accounts.models import Classe, Niveau


class NiveauForm(forms.ModelForm):
    class Meta:
        model = Niveau
        fields = ('code', 'nom', 'ordre', 'actif')
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ex: niveau-1'}),
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom du niveau'}),
            'ordre': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ClasseForm(forms.ModelForm):
    class Meta:
        model = Classe
        fields = ('niveau', 'code', 'nom', 'annee_scolaire', 'capacite', 'actif')
        widgets = {
            'niveau': forms.Select(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ex: A'}),
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ex: Classe A'}),
            'annee_scolaire': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '2025-2026'}),
            'capacite': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


Utilisateur = get_user_model()


class PendingStudentActivationForm(forms.Form):
    student_id = forms.UUIDField(widget=forms.HiddenInput())
    classe = forms.ModelChoiceField(
        queryset=Classe.objects.select_related('niveau').filter(actif=True),
        empty_label='Choisir une classe',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def clean_student_id(self):
        student_id = self.cleaned_data['student_id']
        try:
            user = Utilisateur.objects.get(pk=student_id)
        except Utilisateur.DoesNotExist as exc:
            raise forms.ValidationError('Étudiant introuvable.') from exc
        if user.statut_compte != 'PENDING':
            raise forms.ValidationError('Cet utilisateur n\'est plus en attente.')
        return student_id
