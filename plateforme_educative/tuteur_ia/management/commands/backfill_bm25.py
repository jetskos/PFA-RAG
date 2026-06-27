"""
Management command : backfill_bm25

Peuple la table DocumentChunk depuis les données déjà indexées dans ChromaDB.
À exécuter une seule fois après la migration 0005.

Usage :
    python manage.py backfill_bm25          # backfill tout le ChromaDB
    python manage.py backfill_bm25 --stats  # affiche les compteurs uniquement
    python manage.py backfill_bm25 --clear  # vide la table avant de remplir
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill DocumentChunk (BM25) depuis ChromaDB"

    def add_arguments(self, parser):
        parser.add_argument("--stats", action="store_true", help="Afficher stats uniquement")
        parser.add_argument("--clear", action="store_true", help="Vider la table avant backfill")

    def handle(self, *args, **options):
        from tuteur_ia.tools.chroma_store import get_collection
        from tuteur_ia.models import DocumentChunk

        # ── Stats uniquement ──────────────────────────────────────────────────
        if options["stats"]:
            try:
                col = get_collection()
                chroma_count = col.count()
            except Exception as e:
                chroma_count = f"erreur ({e})"
            db_count = DocumentChunk.objects.count()
            self.stdout.write(f"ChromaDB chunks : {chroma_count}")
            self.stdout.write(f"DB BM25 chunks  : {db_count}")
            return

        # ── Clear ─────────────────────────────────────────────────────────────
        if options["clear"]:
            n = DocumentChunk.objects.count()
            DocumentChunk.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Table vidée ({n} chunks supprimés)"))

        # ── Récupérer tous les chunks depuis ChromaDB ─────────────────────────
        self.stdout.write("Lecture ChromaDB…")
        try:
            col = get_collection()
            total = col.count()
            if total == 0:
                self.stdout.write(self.style.WARNING("ChromaDB est vide, rien à backfiller."))
                return
        except Exception as e:
            self.stderr.write(f"Impossible d'accéder à ChromaDB : {e}")
            return

        # ChromaDB.get() sans filtre récupère tout, mais en batches
        BATCH = 500
        offset = 0
        created = skipped = 0

        while offset < total:
            try:
                result = col.get(
                    include=["documents", "metadatas"],
                    limit=BATCH,
                    offset=offset,
                )
            except Exception as e:
                self.stderr.write(f"Erreur lecture ChromaDB offset={offset} : {e}")
                break

            ids       = result.get("ids", [])
            docs      = result.get("documents", [])
            metas     = result.get("metadatas", [])

            if not ids:
                break

            to_create = []
            existing_ids = set(
                DocumentChunk.objects.filter(chunk_id__in=ids).values_list("chunk_id", flat=True)
            )

            for chunk_id, text, meta in zip(ids, docs, metas):
                if chunk_id in existing_ids:
                    skipped += 1
                    continue
                to_create.append(DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=meta.get("document_id", ""),
                    document_titre=meta.get("document_titre", ""),
                    chapitre_id=meta.get("chapitre_id", ""),
                    cours_id=meta.get("cours_id", ""),
                    page_hint=meta.get("page_hint", ""),
                    chunk_index=int(meta.get("chunk_index", 0) or 0),
                    texte=text or "",
                ))

            if to_create:
                DocumentChunk.objects.bulk_create(to_create, ignore_conflicts=True)
                created += len(to_create)

            offset += len(ids)
            self.stdout.write(f"  {offset}/{total} traités…", ending="\r")

        # Invalider tout le cache BM25
        try:
            from tuteur_ia.tools.bm25_store import invalidate_cache
            invalidate_cache()
        except Exception:
            pass

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Backfill terminé : {created} chunks créés, {skipped} déjà présents."
        ))
