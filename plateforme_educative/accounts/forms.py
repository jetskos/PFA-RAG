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


class AdminUserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '********'}),
        required=False,
        label=_("Mot de passe")
    )
    from .models import Niveau, Classe
    niveau = forms.ModelChoiceField(
        queryset=Niveau.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_("Niveau (Optionnel)")
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '********'}),
        label=_("Mot de passe"),
        required=False
    )

    class Meta:
        model = Utilisateur
        fields = ('first_name', 'last_name', 'email', 'password', 'role', 'niveau')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Jean')}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Dupont')}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'jean.dupont@email.com'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.classe:
                self.initial['niveau'] = self.instance.classe.niveau
        
        # Le mot de passe est obligatoire en création, non modifiable en édition (pour sécurité)
        is_editing = self.instance and not self.instance._state.adding
        if is_editing:
            self.fields.pop('password', None)
        else:
            if 'password' in self.fields:
                self.fields['password'].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        is_creating = not user.pk or user._state.adding
        
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        
        role = self.cleaned_data.get('role', 'ELEVE')
        
        if is_creating:
            user.is_active = (role != 'ELEVE')
            user.statut_compte = 'ACTIVE' if role != 'ELEVE' else 'PENDING'
            user.is_formateur = (role == 'FORMATEUR')
            
            if role == 'ADMIN':
                user.is_staff = True
                user.is_superuser = True
            else:
                user.is_staff = False
                user.is_superuser = False
        else:
            # En édition, on ajuste juste les flags d'accès si le rôle change, 
            # mais on ne désactive pas un élève déjà actif
            user.is_formateur = (role == 'FORMATEUR')
            if role == 'ADMIN':
                user.is_staff = True
                user.is_superuser = True
            elif role == 'ELEVE':
                user.is_staff = False
                user.is_superuser = False

        niveau = self.cleaned_data.get('niveau')
        if niveau:
            from .models import Classe
            import datetime
            classe = Classe.objects.filter(niveau=niveau, actif=True).order_by('annee_scolaire', 'nom').first()
            if not classe:
                current_year = datetime.datetime.now().year
                classe = Classe.objects.create(
                    niveau=niveau,
                    code=f"{niveau.code}-defaut",
                    nom=f"Classe {niveau.nom}",
                    annee_scolaire=f"{current_year}-{current_year+1}",
                    actif=True
                )
            user.classe = classe
        else:
            user.classe = None

        if commit:
            user.save()
        return user