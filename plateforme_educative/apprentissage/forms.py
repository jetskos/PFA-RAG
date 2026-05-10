from django import forms
from .models import Cours, Chapitre, Document


class CoursForm(forms.ModelForm):
    class Meta:
        model = Cours
        fields = ('titre', 'description', 'resume', 'niveau', 'actif')
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'resume': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'niveau': forms.Select(attrs={'class': 'form-control'}),
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
