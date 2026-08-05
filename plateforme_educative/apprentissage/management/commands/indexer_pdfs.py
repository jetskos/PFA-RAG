"""
Management command : indexe tous les PDFs existants dans ChromaDB.

Usage :
    python manage.py indexer_pdfs               # PDFs non encore indexés
    python manage.py indexer_pdfs --force       # Tout réindexer
    python manage.py indexer_pdfs --stats       # Voir les stats ChromaDB
    python manage.py indexer_pdfs --chapitre <uuid>
"""
import os
from django.core.management.base import BaseCommand
from apprentissage.models import Document


class Command(BaseCommand):
    help = "Indexe les PDFs dans ChromaDB (chunking récursif + embeddings)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Réindexer même si déjà fait (vide et recrée les chunks)",
        )
        parser.add_argument(
            "--stats", action="store_true",
            help="Afficher les statistiques ChromaDB et quitter",
        )
        parser.add_argument(
            "--chapitre", type=str, default=None,
            help="UUID du chapitre à traiter uniquement",
        )

    def handle(self, *args, **options):

        # ── Mode stats ──────────────────────────────────────────────────────
        if options["stats"]:
            try:
                from tuteur_ia.tools.chroma_store import get_stats
                stats = get_stats()
                self.stdout.write("\n=== ChromaDB Stats ===")
                for k, v in stats.items():
                    self.stdout.write(f"  {k}: {v}")
                self.stdout.write("")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erreur : {e}"))
            return

        # ── Vérifier les dépendances ─────────────────────────────────────────
        try:
            import pdfplumber  # noqa
        except ImportError:
            self.stdout.write(self.style.ERROR(
                "pdfplumber non installé. Lancez : pip install pdfplumber"
            ))
            return

        try:
            import chromadb  # noqa
        except ImportError:
            self.stdout.write(self.style.ERROR(
                "chromadb non installé. Lancez : pip install chromadb"
            ))
            return



        # ── Récupérer les documents à indexer ────────────────────────────────
        qs = Document.objects.filter(actif=True)
        if options["chapitre"]:
            qs = qs.filter(chapitre_id=options["chapitre"])

        if not options["force"]:
            # Seulement ceux sans contenu_extrait
            qs = qs.filter(contenu_extrait="") | qs.filter(contenu_extrait__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING(
                "Aucun document à traiter. "
                "Utilisez --force pour tout réindexer."
            ))
            return

        self.stdout.write(f"\n Indexation de {total} document(s) dans ChromaDB...\n")

        from tuteur_ia.tools.pdf_extractor import extract_and_chunk_pdf
        from tuteur_ia.tools.chroma_store import add_chunks

        ok = 0
        erreurs = 0

        for doc in qs:
            if not doc.fichier_pdf:
                self.stdout.write(f"  [!] {doc.titre} — pas de fichier PDF")
                continue

            try:
                pdf_path = doc.fichier_pdf.path
            except Exception:
                self.stdout.write(f"  [!] {doc.titre} — chemin PDF invalide")
                continue

            if not os.path.exists(pdf_path):
                self.stdout.write(self.style.WARNING(
                    f"  [X] {doc.titre} — fichier introuvable : {pdf_path}"
                ))
                erreurs += 1
                continue

            try:
                self.stdout.write(f"  -> {doc.titre}...", ending=" ")

                full_text, chunks = extract_and_chunk_pdf(pdf_path)

                if not full_text:
                    self.stdout.write(self.style.WARNING("[!] Vide (PDF scanné ?)"))
                    erreurs += 1
                    continue

                # Sauvegarder contenu_extrait
                Document.objects.filter(pk=doc.pk).update(
                    contenu_extrait=full_text
                )

                # Indexer dans ChromaDB
                add_chunks(
                    chunks=chunks,
                    document_id=str(doc.pk),
                    document_titre=doc.titre,
                    chapitre_id=str(doc.chapitre_id),
                    cours_id=str(doc.chapitre.cours_id),
                )

                self.stdout.write(self.style.SUCCESS(
                    f"[OK] {len(full_text):,} chars, {len(chunks)} chunks"
                ))
                ok += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[X] Erreur : {e}"))
                erreurs += 1

        # -- Résumé -----------------------------------------------------------
        self.stdout.write(f"\n{'-' * 55}")
        self.stdout.write(self.style.SUCCESS(f"[OK] {ok} document(s) indexé(s)"))
        if erreurs:
            self.stdout.write(self.style.WARNING(f"[!] {erreurs} erreur(s)"))

        # Afficher les stats finales
        try:
            from tuteur_ia.tools.chroma_store import get_stats
            stats = get_stats()
            self.stdout.write(
                f"\nChromaDB total : {stats['total_chunks']} chunks "
                f"— {stats['chroma_path']}\n"
            )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Erreur lors de la récupération des statistiques ChromaDB : {e}"))
