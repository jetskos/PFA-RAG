import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings
from django.db import connection

class Command(BaseCommand):
    help = "Restaure un payload de sauvegarde globale (Satellite) et réinitialise le système."

    def add_arguments(self, parser):
        parser.add_argument('zip_file', type=str, help="Chemin vers le fichier ZIP de restauration")

    def handle(self, *args, **kwargs):
        zip_path = Path(kwargs['zip_file'])
        
        if not zip_path.exists() or not zip_path.is_file():
            raise CommandError(f"Le fichier spécifié est introuvable : {zip_path}")

        self.stdout.write(self.style.WARNING("ATTENTION: Cette action va écraser toutes les données existantes dans la base !"))
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            self.stdout.write("Extraction du ZIP...")
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir_path)
            
            dump_file = temp_dir_path / "dump.json"
            if not dump_file.exists():
                raise CommandError("Le fichier dump.json est introuvable à la racine de l'archive ZIP.")

            # 1. Vidage de la base de données (Flush)
            self.stdout.write("Vidage de la base de données (flush)...")
            call_command('flush', interactive=False)

            # 2. Restauration du dossier media
            self.stdout.write("Restauration des fichiers médias...")
            extracted_media_dir = temp_dir_path / "media"
            if extracted_media_dir.exists():
                dest_media_dir = Path(settings.MEDIA_ROOT)
                # Copie récursive en écrasant les fichiers existants
                shutil.copytree(extracted_media_dir, dest_media_dir, dirs_exist_ok=True)
            else:
                self.stdout.write(self.style.NOTICE("Aucun dossier 'media' trouvé dans l'archive."))

            # 3. Chargement de la base de données
            self.stdout.write("Restauration de la base de données depuis dump.json...")
            call_command('loaddata', str(dump_file))
            
            # 4. Rétablissement et indexation AI
            self.stdout.write("Mise à jour des index PDF (RAG) si nécessaire...")
            try:
                call_command('indexer_pdfs')
            except Exception as e:
                self.stdout.write(self.style.NOTICE(f"Note: Échec de l'indexation PDF, peut-être que la commande n'est pas nécessaire: {e}"))

        self.stdout.write(self.style.SUCCESS("✅ Restauration globale terminée avec succès ! Le système est prêt."))
