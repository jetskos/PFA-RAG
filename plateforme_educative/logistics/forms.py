from django import forms
from .models import Ticket, Equipment, DemandeMateriel, Workshop


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['titre', 'description', 'equipement', 'atelier']
        widgets = {
            'titre': forms.TextInput(attrs={'placeholder': 'Titre du ticket', 'class': 'form-input'}),
            'description': forms.Textarea(attrs={'placeholder': 'Décrivez le problème...', 'rows': 5, 'class': 'form-input'}),
            'equipement': forms.Select(attrs={'class': 'form-input'}),
            'atelier': forms.Select(attrs={'class': 'form-input'}),
        }


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['nom', 'numero_serie', 'etat', 'note']
        widgets = {
            'nom': forms.TextInput(attrs={'placeholder': "Nom de l'équipement", 'class': 'form-input'}),
            'numero_serie': forms.TextInput(attrs={'placeholder': 'Numéro de série', 'class': 'form-input'}),
            'etat': forms.Select(attrs={'class': 'form-input'}),
            'note': forms.Textarea(attrs={'placeholder': 'Note interne (optionnel)', 'rows': 3, 'class': 'form-input'}),
        }

    def clean_numero_serie(self):
        numero = self.cleaned_data.get('numero_serie')
        if not numero:
            return numero
        qs = Equipment.objects.filter(numero_serie=numero)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Un équipement avec ce numéro de série existe déjà.')
        return numero


class DemandeMaterielForm(forms.ModelForm):
    class Meta:
        model = DemandeMateriel
        fields = ('equipement', 'atelier_cible', 'quantite')
        widgets = {
            'equipement': forms.Select(attrs={'class': 'form-control'}),
            'atelier_cible': forms.Select(attrs={'class': 'form-control'}),
            'quantite': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atelier_cible'].queryset = Workshop.objects.all().order_by('-date_debut')


class StudentDemandeMaterielForm(forms.ModelForm):
    class Meta:
        model = DemandeMateriel
        fields = ('equipement', 'atelier_cible', 'quantite', 'destinataire')
        widgets = {
            'equipement': forms.Select(attrs={'class': 'form-control'}),
            'atelier_cible': forms.Select(attrs={'class': 'form-control'}),
            'quantite': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 2}),
            'destinataire': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atelier_cible'].queryset = Workshop.objects.all().order_by('-date_debut')
        # Only list active formateurs and admins as possible recipients
        from accounts.models import Utilisateur
        self.fields['destinataire'].queryset = Utilisateur.objects.filter(
            role__in=['ADMIN', 'FORMATEUR'], is_active=True
        ).order_by('role', 'first_name')
        self.fields['destinataire'].label = "Destinataire (Admin ou Formateur)"
        self.fields['destinataire'].required = True

    def clean_quantite(self):
        quantite = self.cleaned_data.get('quantite')
        if quantite is not None:
            if quantite < 1 or quantite > 2:
                raise forms.ValidationError("La quantité demandée doit être comprise entre 1 et 2.")
        return quantite

