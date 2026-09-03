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
import threading
import time
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
_embedding_init_lock = threading.Lock()
_collection_lock = threading.Lock()

# mtime du fichier SQLite de ChromaDB au moment où on a (re)chargé la collection.
# ChromaDB 0.4.x garde l'index HNSW en RAM par process et ne le resynchronise
# pas tout seul : sans ça, le process web ne verrait jamais les documents
# indexés par le worker Celery lors d'un import (le tuteur répond « aucun
# contenu » alors que les chunks existent sur disque).
_collection_disk_mtime = 0.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_chroma_path() -> str:
    """Retourne le chemin de persistance ChromaDB (dans media/ pour persistance Railway)."""
    try:
        from django.conf import settings
        return str(Path(settings.MEDIA_ROOT) / "chroma_db")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Impossible de charger settings.MEDIA_ROOT (fallback utilisé) : {e}")
        return os.path.join(os.getcwd(), "media", "chroma_db")


def _get_embedding_function():
    """Retourne la fonction d'embedding (singleton, création protégée par verrou)."""
    global _embedding_fn
    if _embedding_fn is None:
        with _embedding_init_lock:
            if _embedding_fn is None:
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
                _embedding_fn = DefaultEmbeddingFunction()
                logger.info("Utilisation de DefaultEmbeddingFunction (local ONNX) - pas de PyTorch, API externe inutile !")
    return _embedding_fn


def warm_up_embeddings() -> None:
    """
    Force l'initialisation complète du modèle ONNX (session + tokenizer) tout
    de suite, au lieu d'attendre la première recherche RAG d'un élève.

    L'objet DefaultEmbeddingFunction ne charge réellement le modèle ONNX en
    mémoire qu'au premier appel (cached_property paresseuse) — sans cet appel,
    ce coût d'initialisation retombe sur la première requête utilisateur,
    au pire moment (RAM déjà sollicitée par Django/Ollama).
    """
    _get_embedding_function()(["préchargement"])


def _chroma_marker_mtime() -> float:
    """mtime du fichier SQLite de ChromaDB : avance à chaque écriture, y
    compris depuis un autre process (worker Celery pendant un import)."""
    try:
        return os.path.getmtime(os.path.join(_get_chroma_path(), "chroma.sqlite3"))
    except OSError:
        return 0.0


def _reset_chroma_singletons() -> None:
    """Libère client + collection en cache pour forcer une relecture du disque."""
    global _client, _collection
    try:
        if _client is not None and hasattr(_client, "_system"):
            _client._system.stop()
    except Exception:
        pass
    for _path in (
        "chromadb.api.client",
        "chromadb.api.shared_system_client",
    ):
        try:
            import importlib
            mod = importlib.import_module(_path)
            mod.SharedSystemClient.clear_system_cache()
            break
        except Exception:
            continue
    _client = None
    _collection = None


def get_collection():
    """
    Retourne la collection ChromaDB (singleton, rechargée si le disque a bougé).

    Recharge la collection quand un AUTRE process a écrit dans la base depuis
    notre dernier chargement — indispensable ici : l'import de cours indexe
    via le worker Celery, et le process web garderait sinon un index HNSW
    périmé (tuteur / QCM « aucun contenu » alors que les chunks existent).
    """
    global _client, _collection, _collection_disk_mtime

    if _collection is not None and _chroma_marker_mtime() <= _collection_disk_mtime + 2.0:
        return _collection

    with _collection_lock:
        disk_mtime = _chroma_marker_mtime()
        if _collection is not None and disk_mtime <= _collection_disk_mtime + 2.0:
            return _collection
        if _collection is not None:
            logger.info("[ChromaDB] base modifiée sur disque — rechargement de la collection")
            _reset_chroma_singletons()

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
            _collection_disk_mtime = _chroma_marker_mtime()

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


def _touch_collection_mtime() -> None:
    """À appeler après nos propres écritures : évite de recharger la collection
    juste après (le disque a bougé, mais c'est nous qui l'avons fait)."""
    global _collection_disk_mtime
    _collection_disk_mtime = _chroma_marker_mtime()


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

    # Supprimer les anciens chunks de ce document (re-indexation).
    # Suppression par filtre `where` directement : plus fiable qu'un `get` suivi
    # d'un `delete(ids=...)` quand le cache HNSW du client est désynchronisé
    # (le `get` renvoyait alors [] et les anciens chunks survivaient).
    try:
        collection.delete(where={"document_id": document_id})
    except Exception as e:
        logger.warning(f"Impossible de supprimer les anciens chunks doc {document_id[:8]} : {e}")

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

    # Ajouter par batch de 100 (limite ChromaDB).
    # `upsert` plutôt que `add` : si un ancien chunk de même ID a survécu à la
    # suppression ci-dessus (cache client désynchronisé), on écrase son texte
    # au lieu de le laisser tel quel avec un simple warning « existing ID ».
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i+batch_size],
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
        )

    logger.info(
        f"Indexé {len(chunks)} chunks pour '{document_titre}' "
        f"(doc={document_id[:8]}...)"
    )
    _touch_collection_mtime()  # notre propre écriture : pas besoin de recharger

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
            _touch_collection_mtime()
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

        # Réessai sur échec transitoire (ex. ONNXRuntimeError "bad allocation"
        # observé sous pression mémoire) — évite de dégrader silencieusement
        # une session entière en contexte RAG vide pour un aléa passager.
        results = None
        last_error = None
        for attempt in range(3):
            try:
                results = collection.query(**kwargs)
                break
            except Exception as e:
                last_error = e
                # Fallback : Si la requête filtrée par 'where' échoue (bug ChromaDB "Error finding id"),
                # ré-essayer sans le filtre 'where' puis filtrer les métadonnées en Python.
                if where_filter:
                    try:
                        logger.warning(f"[ChromaDB Fallback] Requête avec filtre where a échoué ({e}), bascule sur filtrage Python.")
                        unfiltered_kwargs = {
                            "query_texts": [query],
                            "n_results":   min(n_results * 5, collection.count()),
                            "include":     ["documents", "metadatas", "distances"],
                        }
                        raw = collection.query(**unfiltered_kwargs)
                        if raw and raw.get("documents") and raw["documents"][0]:
                            f_docs, f_metas, f_dists = [], [], []
                            for doc, meta, dist in zip(raw["documents"][0], raw["metadatas"][0], raw["distances"][0]):
                                if chapitre_id and str(meta.get("chapitre_id")) == str(chapitre_id):
                                    f_docs.append(doc)
                                    f_metas.append(meta)
                                    f_dists.append(dist)
                                elif not chapitre_id and cours_id and str(meta.get("cours_id")) == str(cours_id):
                                    f_docs.append(doc)
                                    f_metas.append(meta)
                                    f_dists.append(dist)
                            
                            if f_docs:
                                results = {
                                    "documents": [f_docs[:n_results]],
                                    "metadatas": [f_metas[:n_results]],
                                    "distances": [f_dists[:n_results]],
                                }
                                break
                    except Exception as fallback_e:
                        logger.warning(f"[ChromaDB Fallback] Échec du filtrage Python : {fallback_e}")

                if attempt < 2:
                    logger.warning(
                        f"Recherche ChromaDB échouée (essai {attempt + 1}/3), nouvelle tentative : {e}"
                    )
                    time.sleep(0.4)
        if results is None:
            raise last_error

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
