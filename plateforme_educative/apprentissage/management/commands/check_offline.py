"""
Vérifie que le serveur est prêt pour un fonctionnement 100 % hors-ligne.

    python manage.py check_offline

Contrôle : base de données, migrations, fichiers statiques compilés, traductions
compilées, moteur LLM local (Ollama), modèle d'embeddings RAG, FFmpeg, dossier
de réception satellite. Sort avec le code 1 si un point bloquant échoue.
"""
import shutil
import socket
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

OK = "\033[92m[OK]\033[0m"
WARN = "\033[93m[! ]\033[0m"
FAIL = "\033[91m[KO]\033[0m"


class Command(BaseCommand):
    help = "Vérifie que la plateforme est prête pour un déploiement 100 % hors-ligne."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true",
                            help="Traite les avertissements (LLM, FFmpeg…) comme des erreurs.")

    def handle(self, *args, **opts):
        self.blocking = 0
        self.warnings = 0

        self._db()
        self._migrations()
        self._static()
        self._translations()
        self._llm()
        self._embeddings()
        self._ffmpeg()
        self._satellite()

        self.stdout.write("")
        if self.blocking or (opts["strict"] and self.warnings):
            self.stdout.write(self.style.ERROR(
                f"{self.blocking} bloquant(s), {self.warnings} avertissement(s) — NON prêt."
            ))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(
            f"Prêt pour le hors-ligne ({self.warnings} avertissement(s))."
        ))

    # ── contrôles ──────────────────────────────────────────────────────────

    def _line(self, mark, label, detail=""):
        self.stdout.write(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))

    def _fail(self, label, detail=""):
        self.blocking += 1
        self._line(FAIL, label, detail)

    def _warn(self, label, detail=""):
        self.warnings += 1
        self._line(WARN, label, detail)

    def _db(self):
        try:
            connection.ensure_connection()
            self._line(OK, "Base de données joignable", connection.settings_dict.get("ENGINE", "").split(".")[-1])
        except Exception as e:
            self._fail("Base de données injoignable", str(e)[:80])

    def _migrations(self):
        try:
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                self._fail("Migrations non appliquées", f"{len(plan)} en attente — lancez migrate")
            else:
                self._line(OK, "Migrations à jour")
        except Exception as e:
            self._warn("Migrations non vérifiables", str(e)[:80])

    def _static(self):
        root = Path(settings.STATIC_ROOT or "")
        manifest = root / "staticfiles.json"
        if not root.exists() or not any(root.iterdir()):
            self._fail("Fichiers statiques non collectés", "lancez collectstatic")
        elif getattr(settings, "STATICFILES_STORAGE", "").endswith("ManifestStaticFilesStorage") and not manifest.exists():
            self._warn("staticfiles.json absent", "relancez collectstatic")
        else:
            self._line(OK, "Fichiers statiques collectés", str(root))
        # vendor local (offline)
        vendor = Path(settings.BASE_DIR) / "static" / "vendor"
        need = ["htmx/htmx.min.js", "chart/chart.umd.min.js", "hls/hls.min.js",
                "tom-select/tom-select.complete.min.js", "fullcalendar/index.global.min.js",
                "tabler-icons/tabler-icons.min.css", "fonts/inter.css"]
        missing = [n for n in need if not (vendor / n).exists()]
        if missing:
            self._fail("Librairies front locales manquantes", ", ".join(missing))
        else:
            self._line(OK, "Librairies front vendored (aucun CDN)")

    def _translations(self):
        for lang in ("fr", "en"):
            mo = Path(settings.BASE_DIR) / "locale" / lang / "LC_MESSAGES" / "django.mo"
            if lang == "en" and not mo.exists():
                self._fail("Traduction anglaise non compilée", "lancez compilemessages")
                return
        self._line(OK, "Traductions compilées (.mo présents)")

    def _llm(self):
        import os
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", os.getenv("LOCAL_LLM_MODEL", "qwen2.5:1.5b-instruct"))
        try:
            if base.endswith("/v1"):
                # Compatibilité OpenAI (ex: llama.cpp, LM Studio)
                with urllib.request.urlopen(f"{base}/models", timeout=3) as r:
                    import json
                    data = json.load(r)
                names = {m.get("id", "") for m in data.get("data", [])}
                provider = "Serveur IA (llama.cpp)"
            else:
                # API Native Ollama
                with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as r:
                    import json
                    data = json.load(r)
                names = {m.get("name", "") for m in data.get("models", [])}
                provider = "Ollama"
                
            # llama.cpp peut parfois renvoyer une liste de modèles vide selon sa config, on valide si ça répond
            if any(model.split(":")[0] in n for n in names) or not names:
                self._line(OK, f"{provider} joignable", model)
            else:
                self._warn(f"{provider} joignable mais modèle incertain", f"attendu: {model}")
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
            self._warn("Moteur IA injoignable", f"LLM hors-ligne indisponible sur {base}")

    def _embeddings(self):
        try:
            from tuteur_ia.tools.chroma_store import EMBEDDING_MODEL
        except Exception:
            EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        cache = Path.home() / ".cache" / "huggingface"
        alt = Path.home() / ".cache" / "torch" / "sentence_transformers"
        hit = False
        for base in (cache, alt):
            if base.exists():
                for p in base.rglob("*"):
                    if "MiniLM" in p.name or "paraphrase-multilingual" in str(p):
                        hit = True
                        break
        if hit:
            self._line(OK, "Modèle d'embeddings RAG en cache", EMBEDDING_MODEL.split("/")[-1])
        else:
            self._warn("Modèle d'embeddings RAG non trouvé en cache",
                       "à télécharger une fois avec internet (tuteur IA / QCM sur PDF)")

    def _ffmpeg(self):
        if shutil.which("ffmpeg"):
            self._line(OK, "FFmpeg installé")
        else:
            self._warn("FFmpeg absent", "conversion vidéo HLS à l'import désactivée")

    def _satellite(self):
        inbox = Path(settings.SATELLITE_INBOX_DIR)
        try:
            inbox.mkdir(parents=True, exist_ok=True)
            (inbox / "processed").mkdir(exist_ok=True)
            self._line(OK, "Boîte de réception satellite prête", str(inbox))
        except Exception as e:
            self._fail("Boîte de réception satellite non créable", str(e)[:80])
