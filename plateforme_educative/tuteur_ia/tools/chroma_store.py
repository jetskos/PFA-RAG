"""
ChromaDB Vector Store Manager.

Gère la collection ChromaDB pour le RAG :
  - Une collection par défaut "pfa_documents"
  - Embeddings via sentence-transformers (local, gratuit)
  - Persistance sur disque dans BASE_DIR/chroma_db/

Ce module est le SEUL endroit qui touche à ChromaDB.
Tous les autres modules (rag_tool, signals) passent par ce manager.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

CHROMA_COLLECTION_NAME = "pfa_documents"

# Modèle d'embedding léger et performant (téléchargé une seule fois)
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Singleton
_client = None
_collection = None
_embedding_fn = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_chroma_path() -> str:
    """Retourne le chemin de persistance ChromaDB (BASE_DIR/chroma_db)."""
    try:
        from django.conf import settings
        return str(Path(settings.BASE_DIR) / "chroma_db")
    except Exception:
        return os.path.join(os.getcwd(), "chroma_db")


def _get_embedding_function():
    """Retourne la fonction d'embedding (singleton)."""
    global _embedding_fn
    if _embedding_fn is None:
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
            _embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            )
            logger.info(f"Modèle d'embedding chargé : {EMBEDDING_MODEL}")
        except ImportError:
            raise ImportError(
                "sentence-transformers non installé. "
                "Lancez : pip install sentence-transformers"
            )
    return _embedding_fn


def get_collection():
    """
    Retourne la collection ChromaDB (singleton).
    Crée le client et la collection si nécessaire.
    """
    global _client, _collection

    if _collection is not None:
        return _collection

    try:
        import chromadb

        chroma_path = _get_chroma_path()
        os.makedirs(chroma_path, exist_ok=True)

        _client = chromadb.PersistentClient(path=chroma_path)
        _collection = _client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            embedding_function=_get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"Collection ChromaDB '{CHROMA_COLLECTION_NAME}' prête "
            f"({_collection.count()} vecteurs) — {chroma_path}"
        )
        return _collection

    except ImportError:
        raise ImportError(
            "chromadb non installé. Lancez : pip install chromadb"
        )
    except Exception as e:
        logger.error(f"Erreur initialisation ChromaDB : {e}")
        raise


# ── Opérations CRUD ──────────────────────────────────────────────────────────

def add_chunks(
    chunks: list[dict],
    document_id: str,
    document_titre: str,
    chapitre_id: str,
    cours_id: str,
):
    """
    Ajoute les chunks d'un document dans ChromaDB.

    Args:
        chunks:         Liste de dicts {text, id, page_hint, ...}
        document_id:    UUID du Document Django
        document_titre: Titre du document (pour affichage)
        chapitre_id:    UUID du Chapitre (pour filtrage RAG)
        cours_id:       UUID du Cours (pour filtrage RAG)
    """
    collection = get_collection()

    # Supprimer les anciens chunks de ce document (re-indexation)
    try:
        existing = collection.get(
            where={"document_id": document_id},
            include=[],
        )
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
            logger.info(f"Supprimé {len(existing['ids'])} anciens chunks pour doc {document_id}")
    except Exception as e:
        logger.warning(f"Impossible de supprimer les anciens chunks : {e}")

    if not chunks:
        logger.warning(f"Aucun chunk à indexer pour document {document_id}")
        return

    ids        = []
    documents  = []
    metadatas  = []

    for chunk in chunks:
        chunk_id = f"{document_id}_chunk_{chunk['id']}"
        ids.append(chunk_id)
        documents.append(chunk["text"])
        metadatas.append({
            "document_id":    document_id,
            "document_titre": document_titre,
            "chapitre_id":    chapitre_id,
            "cours_id":       cours_id,
            "page_hint":      str(chunk.get("page_hint") or ""),
            "chunk_index":    str(chunk["id"]),
        })

    # Ajouter par batch de 100 (limite ChromaDB)
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i+batch_size],
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
        )

    logger.info(
        f"Indexé {len(chunks)} chunks pour '{document_titre}' "
        f"(doc={document_id[:8]}...)"
    )

    # ── Sync DB pour BM25 ────────────────────────────────────────────────────
    try:
        from tuteur_ia.models import DocumentChunk
        from tuteur_ia.tools.bm25_store import invalidate_cache

        # Supprimer anciens chunks du document dans la DB
        DocumentChunk.objects.filter(document_id=document_id).delete()

        # Bulk-create les nouveaux chunks
        db_chunks = [
            DocumentChunk(
                chunk_id=ids[i],
                document_id=document_id,
                document_titre=document_titre,
                chapitre_id=chapitre_id,
                cours_id=cours_id,
                page_hint=metadatas[i].get("page_hint", ""),
                chunk_index=int(metadatas[i].get("chunk_index", i)),
                texte=documents[i],
            )
            for i in range(len(ids))
        ]
        DocumentChunk.objects.bulk_create(db_chunks, ignore_conflicts=True)
        logger.info(f"DB BM25 : {len(db_chunks)} chunks synchronisés pour doc {document_id[:8]}")

        invalidate_cache(chapitre_id=chapitre_id, cours_id=cours_id)
    except Exception as e:
        logger.warning(f"Sync DB BM25 échouée (non bloquant) : {e}")


def delete_document(document_id: str):
    """Supprime tous les chunks d'un document de ChromaDB et de la DB BM25."""
    # Récupérer les métadonnées avant suppression pour invalider le bon cache
    chapitre_id = cours_id = None
    try:
        collection = get_collection()
        existing = collection.get(
            where={"document_id": document_id},
            include=["metadatas"],
        )
        if existing["ids"]:
            if existing.get("metadatas"):
                meta = existing["metadatas"][0]
                chapitre_id = meta.get("chapitre_id")
                cours_id    = meta.get("cours_id")
            collection.delete(ids=existing["ids"])
            logger.info(f"ChromaDB : supprimé {len(existing['ids'])} chunks pour doc {document_id}")
    except Exception as e:
        logger.error(f"Erreur suppression ChromaDB : {e}")

    # ── Sync DB BM25 ─────────────────────────────────────────────────────────
    try:
        from tuteur_ia.models import DocumentChunk
        from tuteur_ia.tools.bm25_store import invalidate_cache
        DocumentChunk.objects.filter(document_id=document_id).delete()
        invalidate_cache(chapitre_id=chapitre_id, cours_id=cours_id)
        logger.info(f"DB BM25 : chunks supprimés pour doc {document_id[:8]}")
    except Exception as e:
        logger.warning(f"Suppression DB BM25 échouée (non bloquant) : {e}")


def search(
    query: str,
    chapitre_id: str = None,
    cours_id: str = None,
    n_results: int = 4,
) -> list[dict]:
    """
    Recherche sémantique dans ChromaDB.

    Args:
        query:       Texte de la requête
        chapitre_id: Filtre sur le chapitre (prioritaire)
        cours_id:    Filtre sur le cours
        n_results:   Nombre de résultats retournés

    Returns:
        Liste de dicts {text, document_titre, distance, page_hint}
    """
    collection = get_collection()

    if collection.count() == 0:
        return []

    # Construire le filtre ChromaDB
    where_filter = None
    if chapitre_id:
        where_filter = {"chapitre_id": {"$eq": chapitre_id}}
    elif cours_id:
        where_filter = {"cours_id": {"$eq": cours_id}}

    try:
        kwargs = {
            "query_texts": [query],
            "n_results":   min(n_results, collection.count()),
            "include":     ["documents", "metadatas", "distances"],
        }
        if where_filter:
            kwargs["where"] = where_filter

        results = collection.query(**kwargs)

        output = []
        docs      = results.get("documents", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for text, meta, dist in zip(docs, metas, distances):
            output.append({
                "text":            text,
                "document_titre":  meta.get("document_titre", ""),
                "page_hint":       meta.get("page_hint", ""),
                "distance":        dist,
                "chapitre_id":     meta.get("chapitre_id", ""),
            })

        return output

    except Exception as e:
        logger.error(f"Erreur recherche ChromaDB : {e}")
        return []


def get_stats() -> dict:
    """Retourne les statistiques de la collection ChromaDB."""
    try:
        collection = get_collection()
        return {
            "total_chunks": collection.count(),
            "collection_name": CHROMA_COLLECTION_NAME,
            "chroma_path": _get_chroma_path(),
            "embedding_model": EMBEDDING_MODEL,
        }
    except Exception as e:
        return {"error": str(e)}
