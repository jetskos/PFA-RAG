import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings

class Command(BaseCommand):
    help = "Génère un payload de sauvegarde globale pour la restauration par satellite."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Début de la génération du payload satellite..."))

        # 1. Préparation du répertoire de sortie
        backup_dir = Path(settings.MEDIA_ROOT) / "satellite_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = backup_dir / f"satellite_payload_{timestamp}.zip"

        # 2. Dossier temporaire pour le dump
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Dump de la base de données
            dump_file = temp_dir_path / "dump.json"
            self.stdout.write("Export de la base de données...")
            
            # On exclut les tables qui causent des conflits à la restauration
            call_command(
                'dumpdata', 
                format='json', 
                output=str(dump_file),
                exclude=['contenttypes', 'auth.Permission', 'sessions', 'admin.logentry']
            )

            # 3. Création de l'archive ZIP
            self.stdout.write("Création de l'archive ZIP (Media + Database)...")
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Ajout du dump.json à la racine du zip
                zipf.write(dump_file, arcname="dump.json")
                
                # Ajout de tout le dossier media (sauf le dossier de backups lui-même)
                media_path = Path(settings.MEDIA_ROOT)
                for root, dirs, files in os.walk(media_path):
                    # Ignorer le dossier de backups pour éviter la récursion infinie
                    if "satellite_backups" in root:
                        continue
                        
                    for file in files:
                        file_path = Path(root) / file
                        arcname = f"media/{file_path.relative_to(media_path)}"
                        zipf.write(file_path, arcname=arcname)

        self.stdout.write(self.style.SUCCESS(f"✅ Payload généré avec succès : {zip_filename}"))
