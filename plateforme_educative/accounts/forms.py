from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

Utilisateur = get_user_model()

class InscriptionForm(UserCreationForm):
    class Meta:
        model = Utilisateur
        fields = ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'ELEVE'
        user.statut_compte = 'PENDING'
        user.is_active = False
        user.classe = None
        
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ('email',)
        widgets = {
            'email': forms.EmailInput(attrs={'autocomplete': 'email', 'class': 'form-control'}),
        }