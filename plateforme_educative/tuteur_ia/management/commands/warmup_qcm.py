"""
Management command : warmup_qcm

Pré-génère les questions QCM de chaque chapitre indexé et les stocke dans
QuestionCache. Une fois le cache chaud, la page QCM répond instantanément
(pas d'appel LLM pendant la requête de l'élève) — indispensable pour une
démo hors-ligne où le LLM local est lent.

Idempotent : un chapitre dont le cache contient déjà `--min` questions est
ignoré. Best-effort : si le moteur IA est indisponible, la commande le
signale et continue sans échouer.

Usage :
    python manage.py warmup_qcm
    python manage.py warmup_qcm --min 8
    python manage.py warmup_qcm --course "Internet of Things"
    python manage.py warmup_qcm --course "English" --lang en --force
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pré-remplit le cache QCM (QuestionCache) pour les chapitres indexés."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min", type=int, default=8,
            help="Nombre minimum de questions à avoir en cache par chapitre (défaut : 8).",
        )
        parser.add_argument(
            "--course", type=str, default="",
            help="Ne traiter que les cours dont le titre contient cette chaîne.",
        )
        parser.add_argument(
            "--lang", type=str, default="",
            help="Langue des questions générées ('fr' | 'en'). "
                 "Par défaut : langue par défaut du site. À utiliser avec "
                 "--course pour un cours dans une autre langue.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Vide le cache des chapitres ciblés avant de régénérer "
                 "(sinon un chapitre déjà chaud est sauté). Utile pour "
                 "régénérer un cours dans la bonne langue.",
        )

    def handle(self, *args, **options):
        from django.utils import translation
        from apprentissage.models import Chapitre
        from tuteur_ia.models import QuestionCache
        from tuteur_ia.views_qcm import _generer_questions_ia

        min_q = max(1, options["min"])
        course_filter = options["course"].strip()

        lang = (options["lang"] or "").strip().lower()[:2]
        if lang in ("fr", "en"):
            translation.activate(lang)
            self.stdout.write(f"Langue des questions : {lang}")

        # La génération loggue chaque échec LLM en ERROR avec la stacktrace ; en
        # warmup c'est du bruit attendu (moteur IA absent). On abaisse le niveau
        # le temps de la commande.
        _qcm_logger = logging.getLogger("tuteur_ia.views_qcm")
        _prev_level = _qcm_logger.level
        _qcm_logger.setLevel(logging.CRITICAL)

        chapitres = Chapitre.objects.filter(actif=True).select_related("cours")
        if course_filter:
            chapitres = chapitres.filter(cours__titre__icontains=course_filter)
        chapitres = list(chapitres.order_by("cours__titre", "ordre"))

        if not chapitres:
            self.stdout.write(self.style.WARNING("Aucun chapitre actif à traiter."))
            return

        force = options["force"]
        done = skipped = failed = 0
        for chapitre in chapitres:
            cache, _ = QuestionCache.objects.get_or_create(chapitre=chapitre)
            if force and cache.questions:
                cache.questions = []
                cache.save()
            pool = cache.questions or []
            if len(pool) >= min_q:
                skipped += 1
                self.stdout.write(f"  = {chapitre.titre[:60]} (cache déjà chaud : {len(pool)})")
                continue

            self.stdout.write(f"  … {chapitre.titre[:60]} — génération IA")
            try:
                questions, reason = _generer_questions_ia(chapitre, n_questions=min_q)
            except Exception as exc:  # pragma: no cover
                failed += 1
                self.stdout.write(self.style.WARNING(f"    échec ({exc})"))
                continue

            if not questions:
                failed += 1
                label = {
                    "no_content": "aucun PDF indexé pour ce chapitre",
                    "llm_unavailable": "moteur IA indisponible",
                }.get(reason, f"génération impossible ({reason})")
                self.stdout.write(self.style.WARNING(f"    ignoré : {label}"))
                if reason == "llm_unavailable":
                    self.stdout.write(self.style.WARNING(
                        "    -> le moteur IA est hors service : arrêt du warmup."
                    ))
                    break
                continue

            existing = {q["question"].strip().lower() for q in pool}
            for q in questions:
                if q["question"].strip().lower() not in existing:
                    pool.append(q)
            cache.questions = pool
            cache.save()
            done += 1
            self.stdout.write(self.style.SUCCESS(f"    {len(pool)} questions en cache"))

        _qcm_logger.setLevel(_prev_level)

        self.stdout.write(self.style.SUCCESS(
            f"\nWarmup QCM terminé : {done} chapitre(s) générés, "
            f"{skipped} déjà chauds, {failed} en échec."
        ))
