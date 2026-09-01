"""
Restaure un payload de sauvegarde globale (Satellite) : vide la base, restaure
les médias, recharge le dump, réindexe le RAG.

    python manage.py restore_satellite snapshot.zip
    python manage.py restore_satellite snapshot.zip --dry-run   # simulation

--dry-run : n'écrit RIEN. Inspecte l'archive (dump.json + médias) et affiche
ce qui serait fait. Code retour 0. Pour un orchestrateur qui coche « simulation »
par défaut avant l'exécution réelle.
"""
import json
import zipfile
import tempfile
import shutil
from pathlib import Path
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings


class Command(BaseCommand):
    help = "Restaure un payload de sauvegarde globale (Satellite) et réinitialise le système."

    def add_arguments(self, parser):
        parser.add_argument('zip_file', type=str, help="Chemin vers le fichier ZIP de restauration")
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Simulation : inspecte l'archive sans rien écrire.",
        )

    # ── simulation ──────────────────────────────────────────────────────────
    def _dry_run(self, zip_path):
        w, s = self.style.WARNING, self.style.SUCCESS
        self.stdout.write(w("=== SIMULATION (--dry-run) - aucune ecriture ==="))
        self.stdout.write(f"Archive : {zip_path}")

        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            if 'dump.json' not in names:
                raise CommandError("dump.json absent a la racine de l'archive : ce n'est pas un snapshot valide.")
            media = [n for n in names if n.startswith('media/') and not n.endswith('/')]
            media_bytes = sum(zf.getinfo(n).file_size for n in media)
            with zf.open('dump.json') as f:
                dump = json.load(f)

        par_modele = Counter(obj.get('model', '?') for obj in dump)
        self.stdout.write(w(f"\n[FLUSH] la base locale serait entierement videe"))
        self.stdout.write(w(f"[LOADDATA] {len(dump)} objet(s) recharges depuis dump.json :"))
        for modele, n in sorted(par_modele.items(), key=lambda kv: -kv[1])[:12]:
            self.stdout.write(f"    {n:>6}  {modele}")
        if len(par_modele) > 12:
            self.stdout.write(f"    ... et {len(par_modele) - 12} autre(s) modele(s)")
        self.stdout.write(w(f"[MEDIA] {len(media)} fichier(s) media ({media_bytes / 1e6:.1f} Mo) copies dans {settings.MEDIA_ROOT}"))
        self.stdout.write(w("[RAG] reindexation des PDF (indexer_pdfs)"))

        self.stdout.write(s(f"\nCommande reelle equivalente :\n  python manage.py restore_satellite \"{zip_path}\""))
        self.stdout.write(s("\n[OK] Simulation terminee - rien n'a ete modifie."))

    # ── exécution réelle ────────────────────────────────────────────────────
    def handle(self, *args, **kwargs):
        zip_path = Path(kwargs['zip_file'])

        if not zip_path.exists() or not zip_path.is_file():
            raise CommandError(f"Le fichier spécifié est introuvable : {zip_path}")

        if kwargs['dry_run']:
            self._dry_run(zip_path)
            return

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

        self.stdout.write(self.style.SUCCESS("[OK] Restauration globale terminée avec succès ! Le système est prêt."))
