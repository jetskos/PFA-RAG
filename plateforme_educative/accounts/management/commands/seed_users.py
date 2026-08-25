import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import IntegrityError

class Command(BaseCommand):
    help = "Génère les comptes utilisateurs de démonstration (Admin, Formateur, Élèves)."

    def handle(self, *args, **kwargs):
        User = get_user_model()
        self.stdout.write(self.style.NOTICE("Création des comptes de test..."))

        # 1. Création de l'Administrateur
        try:
            admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin')
            self.stdout.write(self.style.SUCCESS("✅ Compte Admin créé (admin / admin)"))
        except Exception:
            self.stdout.write(self.style.WARNING("⚠️ Le compte Admin existe déjà."))

        # 2. Création du Formateur
        try:
            formateur = User.objects.create_user(
                username='formateur', 
                email='formateur@example.com', 
                password='formateur',
                is_staff=True
            )
            # Assigner des permissions ou un groupe si nécessaire
            self.stdout.write(self.style.SUCCESS("✅ Compte Formateur créé (formateur / formateur)"))
        except Exception:
            self.stdout.write(self.style.WARNING("⚠️ Le compte Formateur existe déjà."))

        # 3. Création de la classe d'élèves (5 élèves)
        for i in range(1, 6):
            username = f'eleve{i}'
            try:
                User.objects.create_user(
                    username=username, 
                    email=f'{username}@example.com', 
                    password='eleve'
                )
                self.stdout.write(self.style.SUCCESS(f"✅ Compte Élève créé ({username} / eleve)"))
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS("Tous les comptes de démonstration ont été traités !"))
