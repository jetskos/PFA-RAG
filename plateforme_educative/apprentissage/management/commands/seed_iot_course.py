import os
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files import File
from apprentissage.models import Cours, Chapitre, Document
from accounts.models import Niveau, Utilisateur

class Command(BaseCommand):
    help = 'Seeds the database with the IoT course from the local directory.'

    def handle(self, *args, **kwargs):
        source_dir = r"C:\Users\Setup Game\Downloads\courstdtpqcm"
        
        # 1. Préparer l'utilisateur et le niveau
        niveau, _ = Niveau.objects.get_or_create(nom="Licence 3", defaults={'code': 'L3'})
        createur = Utilisateur.objects.filter(role__in=['ADMIN', 'FORMATEUR']).first()
        
        if not createur:
            self.stdout.write(self.style.ERROR("Aucun utilisateur valide (ADMIN ou FORMATEUR) trouvé."))
            return
            
        self.stdout.write(self.style.SUCCESS(f"Création du cours pour le niveau {niveau.nom} par {createur.get_full_name()}..."))

        # 2. Créer le cours
        cours, created = Cours.objects.get_or_create(
            titre="L'Internet des Objets (IoT) : Des Capteurs à l'IA",
            defaults={
                'description': "Dans ce cours complet, découvrez la magie de l'Internet des Objets (IoT). Apprenez comment les objets physiques collectent des données, communiquent entre eux à travers des réseaux invisibles, et utilisent l'intelligence artificielle pour automatiser notre monde.",
                'resume': "Découvrez l'écosystème IoT : capteurs, réseaux, intelligence artificielle et applications pratiques.",
                'niveau': niveau,
                'createur': createur,
                'actif': True
            }
        )
        if not created:
            self.stdout.write(self.style.WARNING("Le cours existe déjà. Suppression des anciens chapitres pour éviter les doublons."))
            cours.chapitres.all().delete()
        
        # Structure des chapitres avec leurs fichiers associés
        structure = [
            {
                "ordre": 1,
                "titre": "Chapitre 1 : Introduction à l'IoT",
                "video": "Les_objets_qui_parlent_!.mp4", 
                "docs": [
                    {"file": "chapite_1.pdf", "type": "COURS", "titre": "Support de Cours - Chapitre 1"},
                    {"file": "td1.pdf", "type": "TP", "titre": "Travaux Dirigés 1"},
                    {"file": "tp1.pdf", "type": "TP", "titre": "Travaux Pratiques 1"},
                    {"file": "qcm1.pdf", "type": "QCM", "titre": "QCM d'évaluation 1"}
                ]
            },
            {
                "ordre": 2,
                "titre": "Chapitre 2 : Comment les objets se parlent (Protocoles)",
                "video": "Comment_les_objets_se_parlent.mp4",
                "docs": [
                    {"file": "chap2pfa2.pdf", "type": "COURS", "titre": "Support de Cours - Chapitre 2"},
                    {"file": "td2.pdf", "type": "TP", "titre": "Travaux Dirigés 2"},
                    {"file": "tdc2.pdf", "type": "RESSOURCE", "titre": "Corrigé TD 2"},
                    {"file": "tp2.pdf", "type": "TP", "titre": "Travaux Pratiques 2"},
                    {"file": "tpc2.pdf", "type": "RESSOURCE", "titre": "Corrigé TP 2"},
                    {"file": "qcm2.pdf", "type": "QCM", "titre": "QCM d'évaluation 2"}
                ]
            },
            {
                "ordre": 3,
                "titre": "Chapitre 3 : Objets Connectés et Réseaux",
                "video": "Objects_That_Speak!.mp4",
                "docs": [
                    {"file": "chap3.pdf", "type": "COURS", "titre": "Support de Cours - Chapitre 3"},
                    {"file": "td3.pdf", "type": "TP", "titre": "Travaux Dirigés 3"},
                    {"file": "tp3.pdf", "type": "TP", "titre": "Travaux Pratiques 3"},
                    {"file": "qcm3.pdf", "type": "QCM", "titre": "QCM d'évaluation 3"}
                ]
            },
            {
                "ordre": 4,
                "titre": "Chapitre 4 : La Toile Invisible (The Invisible Spiderweb)",
                "video": "The_Invisible_Spiderweb.mp4",
                "docs": [
                    {"file": "chap4.pdf", "type": "COURS", "titre": "Support de Cours - Chapitre 4"},
                    {"file": "td4.pdf", "type": "TP", "titre": "Travaux Dirigés 4"},
                    {"file": "qcm4.pdf", "type": "QCM", "titre": "QCM d'évaluation 4"}
                ]
            },
            {
                "ordre": 5,
                "titre": "Chapitre 5 : Quand les machines apprennent (Machine Learning)",
                "video": "Les_machines_peuvent_apprendre.mp4",
                "docs": [
                    {"file": "chapitre5.pdf", "type": "COURS", "titre": "Support de Cours - Chapitre 5"}
                ]
            }
        ]

        # Destination pour les vidéos (on va les copier dans MEDIA_ROOT)
        media_videos_dir = Path(r"C:\Users\Setup Game\Desktop\PFA-RAG-main\plateforme_educative\media\videos")
        media_videos_dir.mkdir(parents=True, exist_ok=True)

        for ch_data in structure:
            self.stdout.write(f"\n--- Création du {ch_data['titre']} ---")
            
            # Copier la vidéo si elle existe
            video_url = ""
            source_video_path = Path(source_dir) / ch_data['video']
            if source_video_path.exists():
                dest_video_path = media_videos_dir / ch_data['video']
                self.stdout.write(f"Copie de la vidéo {ch_data['video']}...")
                shutil.copy2(source_video_path, dest_video_path)
                video_url = f"/media/videos/{ch_data['video']}"
            else:
                self.stdout.write(self.style.WARNING(f"ATTENTION: Vidéo non trouvée: {ch_data['video']}"))

            chapitre = Chapitre.objects.create(
                cours=cours,
                titre=ch_data['titre'],
                ordre=ch_data['ordre'],
                description=f"Dans ce chapitre, nous aborderons les concepts clés de {ch_data['titre'].split(' : ')[-1]}.",
                url_video=video_url,
                actif=True
            )

            # Attacher les documents PDF
            for doc_data in ch_data['docs']:
                source_doc_path = Path(source_dir) / doc_data['file']
                if source_doc_path.exists():
                    self.stdout.write(f"Ajout du document {doc_data['file']}...")
                    with open(source_doc_path, 'rb') as f:
                        django_file = File(f, name=doc_data['file'])
                        Document.objects.create(
                            chapitre=chapitre,
                            titre=doc_data['titre'],
                            type_document=doc_data['type'],
                            fichier_pdf=django_file
                        )
                else:
                    self.stdout.write(self.style.WARNING(f"ATTENTION: Document non trouvé: {doc_data['file']}"))

        self.stdout.write(self.style.SUCCESS(f"\n>>> Seeding terminé avec succès !"))
        self.stdout.write(self.style.SUCCESS(f">>> Cours créé : {cours.titre} avec {cours.chapitres.count()} chapitres."))
