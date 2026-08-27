from django import forms
from .models import Ticket, Equipment, DemandeMateriel, Workshop
from django.utils.translation import gettext_lazy as _


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['titre', 'description', 'equipement', 'atelier']
        widgets = {
            'titre': forms.TextInput(attrs={'placeholder': _('Titre du ticket'), 'class': 'form-input'}),
            'description': forms.Textarea(attrs={'placeholder': _('Décrivez le problème...'), 'rows': 5, 'class': 'form-input'}),
            'equipement': forms.Select(attrs={'class': 'form-input'}),
            'atelier': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['equipement'].empty_label = ""
        self.fields['atelier'].empty_label = ""


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['nom', 'reference', 'stock_total', 'stock_disponible', 'seuil_alerte', 'note']
        labels = {
            'nom': _("Nom de l'équipement"),
            'reference': _('Référence'),
            'stock_total': _('Stock total'),
            'stock_disponible': _('Stock dispo'),
            'seuil_alerte': _("Seuil d'alerte"),
            'note': _('Note (Optionnelle)'),
        }
        widgets = {
            'nom': forms.TextInput(attrs={'placeholder': _("Nom de l'équipement"), 'class': 'form-input'}),
            'reference': forms.TextInput(attrs={'placeholder': _('Référence (unique)'), 'class': 'form-input'}),
            'stock_total': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'stock_disponible': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'note': forms.Textarea(attrs={'placeholder': _('Note interne (optionnel)'), 'rows': 3, 'class': 'form-input'}),
        }

    def clean_reference(self):
        ref = self.cleaned_data.get('reference')
        if not ref:
            return ref
        qs = Equipment.objects.filter(reference=ref)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_('Un équipement avec cette référence existe déjà.'))
        return ref


class WorkshopForm(forms.ModelForm):
    class Meta:
        model = Workshop
        fields = ['titre', 'date_debut', 'date_fin', 'salle', 'tuteur', 'niveau_cible']
        widgets = {
            'titre': forms.TextInput(attrs={'placeholder': _("Titre de l'atelier"), 'class': 'form-input'}),
            'date_debut': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
            'date_fin': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
            'salle': forms.TextInput(attrs={'placeholder': _("Salle (ex: Amphi A)"), 'class': 'form-input'}),
            'tuteur': forms.Select(attrs={'class': 'form-input'}),
            'niveau_cible': forms.TextInput(attrs={'placeholder': _("Niveau cible"), 'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tuteur'].empty_label = ""


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
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and not self.request.user.is_staff:
            self.fields['atelier_cible'].queryset = Workshop.objects.filter(createur=self.request.user).order_by('-date_debut')
        else:
            self.fields['atelier_cible'].queryset = Workshop.objects.all().order_by('-date_debut')
            
        self.fields['equipement'].queryset = Equipment.objects.filter(est_actif=True)
        self.fields['atelier_cible'].empty_label = ""
        self.fields['equipement'].empty_label = ""

    def clean(self):
        cleaned_data = super().clean()
        equipement = cleaned_data.get('equipement')
        quantite = cleaned_data.get('quantite')

        if equipement and quantite:
            if quantite > equipement.stock_disponible:
                self.add_error('quantite', _("Stock insuffisant. Il ne reste que %(n)s unités.") % {'n': equipement.stock_disponible})
        return cleaned_data
