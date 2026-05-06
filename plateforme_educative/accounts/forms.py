from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

Utilisateur = get_user_model()

class InscriptionForm(UserCreationForm):
    class Meta:
        model = Utilisateur
        # On retire 'role' des champs visibles
        fields = ('email',) 

    def save(self, commit=True):
        # On récupère l'utilisateur sans le sauvegarder tout de suite dans la base
        user = super().save(commit=False)
        # On force le rôle à ELEVE par défaut
        user.role = 'ELEVE' 
        
        if commit:
            user.save()
        return user