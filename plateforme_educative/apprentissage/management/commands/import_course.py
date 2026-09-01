"""
Importe un ou plusieurs cours depuis des ZIP d'export, en ligne de commande
(sans passer par l'interface web « Importer (ZIP) »).

    python manage.py import_course cours.zip                          # ajoute, n'efface rien
    python manage.py import_course cours.zip --replace "IoT" -y        # remplace un cours précis
    python manage.py import_course cours.zip --replace-satellite -y    # met à jour SEULEMENT les cours "satellite"
    python manage.py import_course cours.zip --replace-all -y          # réinitialise TOUT le catalogue
    python manage.py import_course cours.zip --replace-satellite --dry-run   # simulation

Modes de suppression (avant l'import) :
- aucun            : n'efface rien (ajoute le cours)
- --replace TITRE  : supprime les cours dont le titre contient TITRE
- --replace-satellite : supprime UNIQUEMENT les cours d'origine "satellite" (source=SATELLITE).
                    Les cours préchargés / créés à la main (source=MANUEL) et les autres
                    imports (source=IMPORT) ne sont PAS touchés. Les nouveaux cours sont
                    marqués source=SATELLITE.
- --replace-all    : supprime TOUS les cours existants (réinitialisation complète).

Autres :
- Le(s) ZIP source(s) ne sont PAS modifiés : l'import travaille sur une copie.
- L'exécution est forcée en mode synchrone (pas besoin d'un worker Celery).
- --replace* supprime aussi les fichiers média associés (couvertures, MP4, PDF, HLS).
- --dry-run : n'écrit RIEN. Affiche ce qui serait supprimé puis importé, code retour 0.
"""
import json
import logging
import shutil
import tempfile
import zipfile
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
            "--replace-satellite", action="store_true",
            help="Supprime d'abord UNIQUEMENT les cours d'origine « satellite », puis importe "
                 "les nouveaux en les marquant « satellite ». Les cours préchargés sont préservés.",
        )
        parser.add_argument(
            "--replace-all", action="store_true",
            help="Supprime TOUS les cours existants avant l'import (réinitialisation complète).",
        )
        parser.add_argument(
            "-y", "--yes", action="store_true",
            help="Ne pas demander de confirmation avant une suppression.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Simulation : affiche ce qui serait supprimé/importé sans rien écrire.",
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

    def _plan(self, opts):
        """Retourne (queryset_a_supprimer | None, libelle, source_a_poser)."""
        from apprentissage.models import Cours
        modes = [opts["replace_all"], opts["replace_satellite"], bool(opts["replace"])]
        if sum(1 for m in modes if m) > 1:
            raise CommandError("Choisir un seul mode : --replace-all OU --replace-satellite OU --replace.")
        if opts["replace_all"]:
            return Cours.objects.all(), "TOUS les cours", "IMPORT"
        if opts["replace_satellite"]:
            return (Cours.objects.filter(source="SATELLITE"),
                    "les cours d'origine « satellite » (les préchargés sont préservés)", "SATELLITE")
        if opts["replace"]:
            return (Cours.objects.filter(titre__icontains=opts["replace"]),
                    f"les cours contenant « {opts['replace']} »", "IMPORT")
        return None, None, "IMPORT"

    def _delete_courses(self, queryset, confirm):
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

    @staticmethod
    def _inspect_zip(path):
        """Lit course_metadata.json dans le ZIP sans rien extraire sur disque."""
        try:
            with zipfile.ZipFile(path) as zf:
                with zf.open("course_metadata.json") as f:
                    meta = json.load(f)
        except KeyError:
            raise CommandError(f"{path.name} : course_metadata.json absent (ce n'est pas un export de cours).")
        except (zipfile.BadZipFile, json.JSONDecodeError) as exc:
            raise CommandError(f"{path.name} : archive illisible ({exc}).")
        cours = meta.get("cours", {})
        chapitres = meta.get("chapitres", [])
        n_docs = sum(len(c.get("documents", [])) for c in chapitres)
        _t = (cours.get("titre") or "Cours importe").strip()
        return {
            "titre": _t if _t.endswith("(Importé)") else f"{_t} (Importé)",
            "niveau": cours.get("niveau") or "NA",
            "chapitres": len(chapitres),
            "documents": n_docs,
            "fichiers_verifies": len(meta.get("checksums", {})),
        }

    def _dry_run(self, zips, user, opts):
        w, s = self.style.WARNING, self.style.SUCCESS
        qs, libelle, source_tag = self._plan(opts)
        self.stdout.write(w("=== SIMULATION (--dry-run) - aucune ecriture base ni fichier ==="))
        self.stdout.write(f"Proprietaire des cours importes : {user.email}")
        self.stdout.write(f"Origine posee sur les nouveaux cours : {source_tag}")

        if qs is None:
            self.stdout.write("\n[EFFACE] rien")
        else:
            self.stdout.write(w(f"\n[EFFACE] {libelle} : {qs.count()} a supprimer"))
            for t in qs.values_list("titre", flat=True):
                self.stdout.write(f"    - {t}")

        self.stdout.write(w("\n[INJECTE] cours qui seraient crees :"))
        for src in zips:
            info = self._inspect_zip(src)
            self.stdout.write(
                f"    + {info['titre']}  [niveau {info['niveau']}, "
                f"{info['chapitres']} chapitre(s), {info['documents']} document(s), "
                f"{info['fichiers_verifies']} fichier(s) verifie(s) par hash]"
            )

        real = "python manage.py import_course " + " ".join(f'"{p}"' for p in zips)
        if opts["as_email"]:
            real += f" --as {opts['as_email']}"
        if opts["replace_all"]:
            real += " --replace-all"
        elif opts["replace_satellite"]:
            real += " --replace-satellite"
        elif opts["replace"]:
            real += f' --replace "{opts["replace"]}"'
        real += " -y"
        self.stdout.write(s(f"\nCommande reelle equivalente :\n  {real}"))
        self.stdout.write(s("\n[OK] Simulation terminee - rien n'a ete modifie."))

    # ── main ─────────────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        from apprentissage.models import ImportJob
        from apprentissage.tasks import import_courses_task

        zips = []
        for raw in opts["zip"]:
            p = Path(raw).expanduser().resolve()
            if not p.is_file():
                raise CommandError(f"Fichier introuvable : {p}")
            zips.append(p)

        user = self._resolve_user(opts["as_email"])
        qs, libelle, source_tag = self._plan(opts)

        if opts["dry_run"]:
            self._dry_run(zips, user, opts)
            return

        self.stdout.write(f"Propriétaire des cours importés : {user.email}")
        self.stdout.write(f"Origine des cours importés : {source_tag}")

        # 1) Efface
        if qs is not None:
            self.stdout.write(self.style.WARNING(f"Suppression : {libelle}..."))
            self._delete_courses(qs, opts["yes"])

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
        # d'échec : on baisse son logger le temps de l'import.
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
                job = ImportJob.objects.create(formateur=user, source=source_tag)
                try:
                    import_courses_task(str(job.id), user.id, [str(tmp)])
                finally:
                    tmp.unlink(missing_ok=True)
                job.refresh_from_db()
                if job.status == "TERMINE":
                    ok += 1
                    self.stdout.write(self.style.SUCCESS(f"  [OK] - {job.titre_cours}"))
                    if job.pdfs_total:
                        line = f"  [INDEX] {job.pdfs_indexes}/{job.pdfs_total} PDF indexes dans ChromaDB"
                        if job.pdfs_indexes < job.pdfs_total:
                            line += ("\n  -> service IA indispo au moment de l'import. "
                                     "Relancer : python manage.py indexer_pdfs")
                            self.stdout.write(self.style.WARNING(line))
                        else:
                            self.stdout.write(self.style.SUCCESS(line))
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
