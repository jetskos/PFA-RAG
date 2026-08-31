"""
Importe un ou plusieurs cours depuis des ZIP d'export, en ligne de commande
(sans passer par l'interface web « Importer (ZIP) »).

    python manage.py import_course cours.zip
    python manage.py import_course cours1.zip cours2.zip --as prof@ecole.ma
    python manage.py import_course cours.zip --replace "IoT Learning Series" -y
    python manage.py import_course cours.zip --replace-all -y

Détails :
- Le(s) ZIP source(s) ne sont PAS modifiés : l'import travaille sur une copie.
- L'exécution est forcée en mode synchrone (pas besoin d'un worker Celery).
- --replace / --replace-all suppriment aussi les fichiers média associés
  (couvertures, MP4, PDF) pour éviter les orphelins entre deux « efface / injecte ».
"""
import logging
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Importe des cours depuis des ZIP d'export (équivalent CLI du bouton « Importer (ZIP) »)."

    def add_arguments(self, parser):
        parser.add_argument(
            "zip", nargs="+",
            help="Chemin(s) vers le(s) fichier(s) ZIP d'export de cours.",
        )
        parser.add_argument(
            "--as", dest="as_email", default=None,
            help="E-mail du propriétaire (formateur/admin). Défaut : 1er superuser, sinon 1er ADMIN.",
        )
        parser.add_argument(
            "--replace", metavar="TITRE", default=None,
            help="Supprime d'abord les cours dont le titre CONTIENT TITRE (insensible à la casse).",
        )
        parser.add_argument(
            "--replace-all", action="store_true",
            help="Supprime TOUS les cours existants avant l'import.",
        )
        parser.add_argument(
            "-y", "--yes", action="store_true",
            help="Ne pas demander de confirmation avant une suppression.",
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    def _resolve_user(self, email):
        from accounts.models import Utilisateur
        if email:
            try:
                return Utilisateur.objects.get(email__iexact=email.strip())
            except Utilisateur.DoesNotExist:
                raise CommandError(f"Aucun utilisateur avec l'e-mail « {email} ».")
        user = (Utilisateur.objects.filter(is_superuser=True).order_by("date_creation").first()
                or Utilisateur.objects.filter(role="ADMIN").order_by("date_creation").first())
        if not user:
            raise CommandError("Aucun superuser ni ADMIN trouvé. Précisez --as <email>.")
        return user

    def _delete_courses(self, queryset, confirm):
        from apprentissage.models import Cours
        titres = list(queryset.values_list("titre", flat=True))
        if not titres:
            self.stdout.write("  (aucun cours à supprimer)")
            return
        self.stdout.write(self.style.WARNING(f"  {len(titres)} cours vont être supprimés :"))
        for t in titres:
            self.stdout.write(f"    - {t}")
        if not confirm:
            rep = input("  Confirmer la suppression ? [oui/NON] ").strip().lower()
            if rep not in {"oui", "o", "yes", "y"}:
                raise CommandError("Suppression annulée.")

        media_root = Path(settings.MEDIA_ROOT)
        removed_files = 0
        for cours in queryset.prefetch_related("chapitres__documents"):
            for chap in cours.chapitres.all():
                for doc in chap.documents.all():
                    removed_files += self._unlink_field(doc.fichier_pdf)
                removed_files += self._unlink_field(chap.video_fichier)
                # dossier HLS éventuel
                if getattr(chap, "video_hls_url", ""):
                    hls_dir = (media_root / chap.video_hls_url).parent
                    if hls_dir.is_dir() and media_root in hls_dir.parents:
                        shutil.rmtree(hls_dir, ignore_errors=True)
            removed_files += self._unlink_field(cours.image_couverture)
        deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(
            f"  {len(titres)} cours supprimés ({deleted} objets, {removed_files} fichiers média)."
        ))

    @staticmethod
    def _unlink_field(filefield):
        try:
            if filefield and filefield.name:
                p = Path(filefield.path)
                if p.is_file():
                    p.unlink()
                    return 1
        except (ValueError, OSError):
            pass
        return 0

    # ── main ─────────────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        from apprentissage.models import Cours, ImportJob
        from apprentissage.tasks import import_courses_task

        zips = []
        for raw in opts["zip"]:
            p = Path(raw).expanduser().resolve()
            if not p.is_file():
                raise CommandError(f"Fichier introuvable : {p}")
            zips.append(p)

        user = self._resolve_user(opts["as_email"])
        self.stdout.write(f"Propriétaire des cours importés : {user.email}")

        # 1) Efface
        if opts["replace_all"]:
            self.stdout.write(self.style.WARNING("Suppression de TOUS les cours..."))
            self._delete_courses(Cours.objects.all(), opts["yes"])
        elif opts["replace"]:
            self.stdout.write(self.style.WARNING(f"Suppression des cours contenant « {opts['replace']} »..."))
            self._delete_courses(Cours.objects.filter(titre__icontains=opts["replace"]), opts["yes"])

        # 2) Injecte — exécution synchrone forcée (aucun worker requis)
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = False
        try:
            from core.celery import app as celery_app
            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = False
        except Exception:
            pass

        # L'indexation IA des PDF (ChromaDB) est optionnelle et bruyante en cas
        # d'échec : on baisse son logger le temps de l'import. À relancer au
        # besoin avec « python manage.py indexer_pdfs ».
        tasks_logger = logging.getLogger("apprentissage.tasks")
        prev_level = tasks_logger.level
        tasks_logger.setLevel(logging.CRITICAL)

        ok, failed = 0, 0
        try:
            for src in zips:
                self.stdout.write(f"\n> Import de {src.name} ...")
                # L'import supprime le ZIP qu'on lui passe : on travaille sur une copie.
                tmp = Path(tempfile.gettempdir()) / f"import_{timezone.now():%Y%m%d%H%M%S}_{src.name}"
                shutil.copy2(src, tmp)
                job = ImportJob.objects.create(formateur=user)
                try:
                    import_courses_task(str(job.id), user.id, [str(tmp)])
                finally:
                    tmp.unlink(missing_ok=True)
                job.refresh_from_db()
                if job.status == "TERMINE":
                    ok += 1
                    self.stdout.write(self.style.SUCCESS(f"  [OK] - {job.titre_cours}"))
                else:
                    failed += 1
                    self.stdout.write(self.style.ERROR(
                        f"  [ECHEC] ({job.status}) - {job.erreur or 'voir les logs'}"))
        finally:
            tasks_logger.setLevel(prev_level)

        self.stdout.write("")
        summary = f"Terminé : {ok} cours importé(s), {failed} échec(s)."
        self.stdout.write(self.style.SUCCESS(summary) if failed == 0 else self.style.ERROR(summary))
        if failed:
            raise SystemExit(1)
