from django import forms
from .models import Ticket, Equipment


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
