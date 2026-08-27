from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

Utilisateur = get_user_model()

class InscriptionForm(UserCreationForm):
    class Meta:
        model = Utilisateur
        fields = ('first_name', 'last_name', 'email',)
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Votre prénom')}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Votre nom')}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': _('votre.email@exemple.com')}),
        }

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
    # Case à cocher virtuelle (pas en base) pour retirer l'avatar courant
    supprimer_photo = forms.BooleanField(required=False, label=_('Supprimer la photo actuelle'))

    class Meta:
        model = Utilisateur
        fields = ('first_name', 'last_name', 'email', 'photo')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email', 'class': 'form-control'}),
            # input file masqué : déclenché par un bouton stylé côté template
            'photo': forms.ClearableFileInput(attrs={
                'class': 'photo-input',
                'accept': 'image/*',
                'id': 'id_photo',
            }),
        }


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label=_("Courriel"),
        max_length=254,
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email',
            'required': True,
            'placeholder': _('votre.email@exemple.com')
        })
    )

from .models import ConfigurationSysteme

class ConfigurationSystemeForm(forms.ModelForm):
    class Meta:
        model = ConfigurationSysteme
        fields = ['mode_hors_ligne', 'llm_provider', 'activer_hls']
        widgets = {
            'mode_hors_ligne': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'llm_provider': forms.Select(attrs={'class': 'form-control'}),
            'activer_hls': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }