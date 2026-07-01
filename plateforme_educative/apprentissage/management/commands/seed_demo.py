import os
import shutil
from datetime import timedelta
from django.utils import timezone
from django.core.files import File
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from accounts.models import Utilisateur, Niveau, Classe
from apprentissage.models import Cours, Chapitre, Devoir, Document

class Command(BaseCommand):
    help = 'Génère la base de données démo Génération Smart (Primaire)'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- Lancement du Seeder : Génération Smart ---")

        # Fichier PDF de base (placeholder pour tous les documents)
        pdf_source = 'media/documents/2026/06/chapite_1.pdf'
        has_pdf = os.path.exists(pdf_source)
        if not has_pdf:
            self.stdout.write(self.style.WARNING(f"ATTENTION : Fichier {pdf_source} introuvable. Les PDF seront créés sans vrai fichier, ce qui peut bloquer RAG."))

        # 1. Niveau & Classe
        niveau, _ = Niveau.objects.get_or_create(nom="Débutant (Primaire)", defaults={'ordre': 1})
        classe, _ = Classe.objects.get_or_create(nom="Génération Smart", annee_scolaire="2025-2026", defaults={'niveau': niveau})
        self.stdout.write(self.style.SUCCESS("Niveau 'Débutant (Primaire)' et Classe créés."))

        # 2. Utilisateurs
        formateur, _ = Utilisateur.objects.get_or_create(email='prof@smart.com', defaults={
            'first_name': 'Prof', 'last_name': 'Smart', 'role': 'FORMATEUR', 'is_formateur': True,
            'statut_compte': 'ACTIVE', 'is_active': True, 'password': make_password('prof123')
        })
        
        for i in range(1, 4):
            Utilisateur.objects.get_or_create(email=f'enfant{i}@smart.com', defaults={
                'first_name': 'Enfant', 'last_name': str(i), 'role': 'ELEVE', 'classe': classe,
                'statut_compte': 'ACTIVE', 'is_active': True, 'password': make_password('enfant123')
            })
        self.stdout.write(self.style.SUCCESS("Professeur et Élèves créés."))

        # 3. Cours
        cours, _ = Cours.objects.get_or_create(
            titre="Génération Smart : La Technologie expliquée aux enfants",
            createur=formateur,
            defaults={
                'description': "Bienvenue sur Génération Smart ! Découvre les secrets des objets connectés, de l'IA et des maisons intelligentes en t'amusant.",
                'niveau': niveau,
                'resume': "La chaîne où la technologie devient un jeu d'enfant !",
                'actif': True
            }
        )

        # 4. Chapitres, Documents et Devoirs (Basé sur les vidéos YouTube)
        chapitres_data = [
            {
                "titre": "Dans les secrets des objets connectés ?! Mon monde, mes ordres !",
                "desc": "Je présente mon invention ! L'Aventure avec Nova. Découvre comment les objets autour de toi communiquent.",
                "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Remplacer par la vraie URL
                "tp_titre": "Dessine ton premier objet connecté",
                "tp_desc": "Imagine un objet de ton quotidien. Comment pourrait-il être connecté pour t'aider ? Dessine-le et explique ses fonctions.",
                "doc_titre": "TD_Objets_Connectes.pdf",
                "doc_type": "TP"
            },
            {
                "titre": "La maison intelligente : quand ta maison t'aide toute seule !",
                "desc": "Ma maison, mon super-héros. Apprends comment une maison peut allumer la lumière ou faire le café toute seule.",
                "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Remplacer par la vraie URL
                "tp_titre": "Mission : Maison Intelligente",
                "tp_desc": "Liste 3 choses que ta maison intelligente ferait pour toi le matin avant d'aller à l'école.",
                "doc_titre": "TD_Maison_Intelligente.pdf",
                "doc_type": "ATELIER"
            },
            {
                "titre": "Les machines peuvent-elles APPRENDRE ? L'IA expliquée aux enfants",
                "desc": "Ils apprennent ?! Découvre ce qu'est l'Intelligence Artificielle et comment un robot apprend à reconnaître un chat.",
                "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Remplacer par la vraie URL
                "tp_titre": "Apprends à ton robot",
                "tp_desc": "Choisis un animal. Quelles sont les 3 règles (oreilles, poils, etc.) que tu donnerais à ton robot pour qu'il le reconnaisse ?",
                "doc_titre": "Cours_IA_Enfants.pdf",
                "doc_type": "COURS"
            },
            {
                "titre": "Où va l'info ? WiFi, Bluetooth, Cloud",
                "desc": "Le chemin magique d'internet. Comment les informations voyagent dans les airs !",
                "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Remplacer par la vraie URL
                "tp_titre": "Le parcours du message",
                "tp_desc": "Trace sur une feuille le chemin qu'emprunte un message de ton téléphone jusqu'à celui de ton ami.",
                "doc_titre": "Ressource_Reseaux.pdf",
                "doc_type": "RESSOURCE"
            },
            {
                "titre": "Ils parlent pour de vrai ?! Assistants vocaux",
                "desc": "Coucou, tu bois quoi ?! Je t'ai fait un toast ! Découvre comment les machines comprennent la voix humaine.",
                "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Remplacer par la vraie URL
                "tp_titre": "Crée ta commande vocale",
                "tp_desc": "Invente la commande vocale parfaite pour faire tes devoirs plus vite.",
                "doc_titre": "TP_Assistants_Vocaux.pdf",
                "doc_type": "TP"
            }
        ]

        # Nettoyage des anciens chapitres pour éviter les doublons lors des re-tests
        Chapitre.objects.filter(cours=cours).delete()

        for idx, c_data in enumerate(chapitres_data, 1):
            chapitre = Chapitre.objects.create(
                cours=cours,
                titre=c_data['titre'],
                description=c_data['desc'],
                ordre=idx,
                url_video=c_data['url']
            )

            # Création du devoir (TP)
            Devoir.objects.create(
                chapitre=chapitre,
                titre=c_data['tp_titre'],
                consigne=c_data['tp_desc'],
                date_limite=timezone.now() + timedelta(days=7),
                note_max=20,
                createur=formateur,
                actif=True
            )

            # Création du document PDF
            if has_pdf:
                with open(pdf_source, 'rb') as f:
                    Document.objects.create(
                        chapitre=chapitre,
                        titre=c_data['doc_titre'],
                        type_document=c_data['doc_type'],
                        fichier_pdf=File(f, name=f"seed_{c_data['doc_titre']}"),
                        ordre=1,
                        description=f"Fichier support pour le chapitre : {c_data['titre']}"
                    )
            
            self.stdout.write(f"  - Chapitre {idx} cree : {c_data['titre']}")

        self.stdout.write(self.style.SUCCESS("\nBase de donnees Generation Smart initialisee !"))
        self.stdout.write(self.style.WARNING("-> Compte Formateur : prof@smart.com (mdp: prof123)"))
        self.stdout.write(self.style.WARNING("-> Compte Eleve : enfant1@smart.com (mdp: enfant123)"))
