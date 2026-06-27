"""
Reciprocal Rank Fusion (RRF).

Fusionne plusieurs listes de résultats de recherche (sémantique + BM25)
en une liste unique pondérée par les rangs.

Formule :  RRF(d) = Σ  1 / (k + rank_i(d))
           k = 60  (valeur standard Cormack et al. 2009)

Avantages par rapport à une normalisation de scores :
  - Agnostique aux distributions de scores de chaque système
  - Robuste aux outliers
  - Pas besoin de calibration
"""

RRF_K = 60  # Constante d'amortissement standard


def rrf_fuse(
    *ranked_lists: list[dict],
    id_key: str = "chunk_id",
    n_results: int = 4,
) -> list[dict]:
    """
    Fusionne N listes de résultats via Reciprocal Rank Fusion.

    Args:
        *ranked_lists : Listes de dicts, chacune triée du plus au moins pertinent.
                        Chaque dict DOIT contenir le champ `id_key`.
        id_key        : Clé servant d'identifiant unique d'un chunk.
        n_results     : Nombre de résultats finaux à retourner.

    Returns:
        Liste de dicts fusionnés, triés par score RRF décroissant.
        Chaque dict contient toutes les clés du dict source +
        {"rrf_score": float, "sources": list[str]}.
    """
    # Accumulateur : chunk_id → {rrf_score, payload, sources}
    scores: dict[str, dict] = {}

    for list_idx, ranked in enumerate(ranked_lists):
        source_name = f"list_{list_idx}"
        for rank, item in enumerate(ranked, start=1):
            cid = item.get(id_key)
            if not cid:
                continue
            contribution = 1.0 / (RRF_K + rank)
            if cid not in scores:
                scores[cid] = {
                    "rrf_score": 0.0,
                    "payload":   item,
                    "sources":   [],
                }
            scores[cid]["rrf_score"] += contribution
            scores[cid]["sources"].append(source_name)

    # Trier par score RRF décroissant
    ranked_fused = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)

    # Reconstituer la liste finale
    results = []
    for entry in ranked_fused[:n_results]:
        item = dict(entry["payload"])
        item["rrf_score"] = round(entry["rrf_score"], 6)
        item["retrieval_sources"] = entry["sources"]
        results.append(item)

    return results
