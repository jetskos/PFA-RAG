from django import forms
from .models import Cours, Chapitre, Document, Devoir, Soumission


class CoursForm(forms.ModelForm):
    class Meta:
        model = Cours
        fields = ('titre', 'description', 'resume', 'niveau', 'image_couverture', 'actif')
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'resume': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'niveau': forms.Select(attrs={'class': 'form-control'}),
            'image_couverture': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ChapitreForm(forms.ModelForm):
    class Meta:
        model = Chapitre
        fields = ('titre', 'description', 'ordre', 'url_video', 'actif')
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ordre': forms.NumberInput(attrs={'class': 'form-control'}),
            'url_video': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://youtube.com/watch?v=...'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class DocumentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['fichier_pdf'].required = False

    class Meta:
        model = Document
        fields = ('titre', 'type_document', 'fichier_pdf', 'description', 'ordre', 'actif')
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'type_document': forms.Select(attrs={'class': 'form-control'}),
            'fichier_pdf': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ordre': forms.NumberInput(attrs={'class': 'form-control'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class DevoirForm(forms.ModelForm):
    """Formulaire de création/modification d'un devoir (formateur)."""

    class Meta:
        model = Devoir
        fields = ('titre', 'consigne', 'fichier_consigne', 'date_limite', 'actif')
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Titre du devoir'}),
            'consigne': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Décrivez la consigne...'}),
            'fichier_consigne': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png'}),
            'date_limite': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fichier_consigne'].required = False
        self.fields['date_limite'].required = False
        if self.instance and self.instance.pk:
            self.fields['fichier_consigne'].required = False
        # Format pour datetime-local
        if self.instance and self.instance.date_limite:
            self.initial['date_limite'] = self.instance.date_limite.strftime('%Y-%m-%dT%H:%M')

        # Griser les dates passées
        from django.utils import timezone
        now_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')
        self.fields['date_limite'].widget.attrs['min'] = now_str


class SoumissionForm(forms.ModelForm):
    """Formulaire de dépôt d'une soumission (élève)."""

    class Meta:
        model = Soumission
        fields = ('fichier', 'commentaire_eleve')
        widgets = {
            'fichier': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png'}),
            'commentaire_eleve': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Commentaire facultatif...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si c'est un remplacement, le fichier n'est pas obligatoire
        if self.instance and self.instance.pk:
            self.fields['fichier'].required = False


class NotationSoumissionForm(forms.ModelForm):
    """Formulaire de notation d'une soumission (formateur)."""

    class Meta:
        model = Soumission
        fields = ('note', 'feedback')
        widgets = {
            'note': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 20, 'step': '0.25', 'placeholder': 'Ex: 16.5'}),
            'feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Commentaire et retour pour l\'élève...'}),
        }

    def clean_note(self):
        note = self.cleaned_data.get('note')
        if note is not None:
            if note < 0 or note > 20:
                raise forms.ValidationError("La note doit être comprise entre 0 et 20.")
        return note


from .models import Evenement

class EvenementForm(forms.ModelForm):
    class Meta:
        model = Evenement
        fields = ('titre', 'description', 'type', 'date_debut', 'date_fin', 'cours', 'classe')
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de l\'événement'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Description...'}),
            'type': forms.Select(attrs={'class': 'form-control'}),
            'date_debut': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'date_fin': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'cours': forms.Select(attrs={'class': 'form-control'}),
            'classe': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_fin'].required = False
        self.fields['cours'].required = False
        self.fields['classe'].required = False
        if self.instance and self.instance.date_debut:
            self.initial['date_debut'] = self.instance.date_debut.strftime('%Y-%m-%dT%H:%M')
        if self.instance and self.instance.date_fin:
            self.initial['date_fin'] = self.instance.date_fin.strftime('%Y-%m-%dT%H:%M')

        # Griser les dates passées
        from django.utils import timezone
        now_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')
        self.fields['date_debut'].widget.attrs['min'] = now_str
        self.fields['date_fin'].widget.attrs['min'] = now_str


