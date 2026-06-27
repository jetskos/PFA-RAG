"""
Tests — Recherche hybride BM25 + RRF

Vérifie le pipeline complet : BM25Store, RRF fusion, et rag_search().

Run : python manage.py test tuteur_ia.tests.test_hybrid_search
"""
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase

from tuteur_ia.models import DocumentChunk
from tuteur_ia.tools.bm25_store import bm25_search, invalidate_cache, _tokenize
from tuteur_ia.tools.rrf import rrf_fuse


# ── Tokenizer ─────────────────────────────────────────────────────────────────

class TokenizerTest(TestCase):

    def test_removes_stopwords(self):
        tokens = _tokenize("le chat est sur le tapis")
        self.assertNotIn("le", tokens)
        self.assertNotIn("est", tokens)
        self.assertNotIn("sur", tokens)
        self.assertIn("chat", tokens)
        self.assertIn("tapis", tokens)

    def test_removes_short_tokens(self):
        tokens = _tokenize("un ox est là")
        self.assertNotIn("ox", tokens)   # 2 chars
        self.assertNotIn("là", tokens)   # 2 chars after NFD

    def test_normalises_accents(self):
        tokens = _tokenize("élève étudie école")
        # Après normalisation NFD, accents supprimés → "eleve", "etudie", "ecole"
        self.assertIn("eleve", tokens)
        self.assertIn("etudie", tokens)
        self.assertIn("ecole", tokens)

    def test_empty_string(self):
        self.assertEqual(_tokenize(""), [])


# ── BM25Store ─────────────────────────────────────────────────────────────────

class BM25SearchTest(TestCase):

    def setUp(self):
        self.chapitre_id = str(uuid.uuid4())
        self.cours_id = str(uuid.uuid4())
        invalidate_cache()  # vide le cache avant chaque test

        # BM25Okapi a besoin d'au moins 3 documents dans le corpus pour avoir
        # des scores IDF positifs (avec N=2, df=1 → IDF=0 car clippé).
        DocumentChunk.objects.create(
            chunk_id="chunk-1",
            document_id=str(uuid.uuid4()),
            document_titre="Cours de mathématiques",
            chapitre_id=self.chapitre_id,
            cours_id=self.cours_id,
            texte="Les fractions représentent une partie d'un tout. Par exemple, 1/2 est une moitié.",
            chunk_index=0,
        )
        DocumentChunk.objects.create(
            chunk_id="chunk-2",
            document_id=str(uuid.uuid4()),
            document_titre="Cours de mathématiques",
            chapitre_id=self.chapitre_id,
            cours_id=self.cours_id,
            texte="La multiplication est une addition répétée. Multiplier 3 par 4 donne 12.",
            chunk_index=1,
        )
        DocumentChunk.objects.create(
            chunk_id="chunk-2b",
            document_id=str(uuid.uuid4()),
            document_titre="Cours de mathématiques",
            chapitre_id=self.chapitre_id,
            cours_id=self.cours_id,
            texte="La géométrie étudie les formes et les surfaces planes et solides.",
            chunk_index=2,
        )
        DocumentChunk.objects.create(
            chunk_id="chunk-3",
            document_id=str(uuid.uuid4()),
            document_titre="Cours de sciences",
            chapitre_id=str(uuid.uuid4()),  # autre chapitre
            cours_id=self.cours_id,
            texte="La photosynthèse permet aux plantes de fabriquer de l'énergie.",
            chunk_index=0,
        )

    def tearDown(self):
        invalidate_cache()

    def test_returns_relevant_chunk(self):
        results = bm25_search("fractions partie tout", chapitre_id=self.chapitre_id)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["chunk_id"], "chunk-1")

    def test_filters_by_chapitre(self):
        results = bm25_search("cours", chapitre_id=self.chapitre_id)
        chunk_ids = [r["chunk_id"] for r in results]
        self.assertNotIn("chunk-3", chunk_ids)

    def test_returns_empty_for_unknown_chapitre(self):
        results = bm25_search("fractions", chapitre_id="nonexistent")
        self.assertEqual(results, [])

    def test_scores_are_positive(self):
        results = bm25_search("multiplication addition", chapitre_id=self.chapitre_id)
        for r in results:
            self.assertGreater(r["bm25_score"], 0)

    def test_result_has_required_keys(self):
        results = bm25_search("fractions", chapitre_id=self.chapitre_id)
        self.assertTrue(len(results) > 0)
        r = results[0]
        for key in ("chunk_id", "text", "document_titre", "page_hint", "chapitre_id", "bm25_score"):
            self.assertIn(key, r)

    def test_empty_query_returns_empty(self):
        results = bm25_search("", chapitre_id=self.chapitre_id)
        self.assertEqual(results, [])

    def test_cache_invalidation(self):
        bm25_search("fractions", chapitre_id=self.chapitre_id)  # popule le cache
        # Invalider avec le même filtre que la recherche (chapitre_id seul)
        invalidate_cache(chapitre_id=self.chapitre_id)
        # Après invalidation, une nouvelle recherche doit toujours fonctionner
        results = bm25_search("fractions", chapitre_id=self.chapitre_id)
        self.assertTrue(len(results) > 0)


# ── RRF Fusion ────────────────────────────────────────────────────────────────

class RRFFuseTest(TestCase):

    def _make_list(self, ids):
        return [{"chunk_id": cid, "text": f"texte {cid}"} for cid in ids]

    def test_merges_two_lists(self):
        list1 = self._make_list(["a", "b", "c"])
        list2 = self._make_list(["b", "a", "d"])
        fused = rrf_fuse(list1, list2, id_key="chunk_id", n_results=4)
        ids = [r["chunk_id"] for r in fused]
        # 'a' et 'b' sont dans les deux listes → scores plus élevés
        self.assertIn("a", ids)
        self.assertIn("b", ids)

    def test_top_result_is_in_both_lists(self):
        list1 = self._make_list(["shared", "only1"])
        list2 = self._make_list(["shared", "only2"])
        fused = rrf_fuse(list1, list2, id_key="chunk_id", n_results=3)
        self.assertEqual(fused[0]["chunk_id"], "shared")

    def test_respects_n_results(self):
        list1 = self._make_list(["a", "b", "c", "d", "e"])
        list2 = self._make_list(["e", "d", "c", "b", "a"])
        fused = rrf_fuse(list1, list2, id_key="chunk_id", n_results=3)
        self.assertEqual(len(fused), 3)

    def test_has_rrf_score(self):
        list1 = self._make_list(["x"])
        fused = rrf_fuse(list1, id_key="chunk_id", n_results=1)
        self.assertIn("rrf_score", fused[0])
        self.assertGreater(fused[0]["rrf_score"], 0)

    def test_has_retrieval_sources(self):
        list1 = self._make_list(["x"])
        list2 = self._make_list(["x"])
        fused = rrf_fuse(list1, list2, id_key="chunk_id", n_results=1)
        self.assertEqual(len(fused[0]["retrieval_sources"]), 2)

    def test_empty_inputs(self):
        fused = rrf_fuse([], [], id_key="chunk_id", n_results=4)
        self.assertEqual(fused, [])

    def test_single_list(self):
        list1 = self._make_list(["a", "b"])
        fused = rrf_fuse(list1, id_key="chunk_id", n_results=2)
        self.assertEqual(len(fused), 2)

    def test_items_without_id_are_skipped(self):
        list1 = [{"text": "sans id"}, {"chunk_id": "ok", "text": "avec id"}]
        fused = rrf_fuse(list1, id_key="chunk_id", n_results=2)
        self.assertEqual(len(fused), 1)
        self.assertEqual(fused[0]["chunk_id"], "ok")


# ── rag_search (integration légère) ──────────────────────────────────────────

class RagSearchTest(TestCase):

    def test_returns_string(self):
        from tuteur_ia.tools.rag_tool import rag_search
        # Sans chunks → message informatif
        result = rag_search("test", chapitre_id=str(uuid.uuid4()))
        self.assertIsInstance(result, str)

    def test_returns_no_doc_message_when_empty(self):
        from tuteur_ia.tools.rag_tool import rag_search
        with patch("tuteur_ia.tools.chroma_store.get_stats", return_value={"total_chunks": 0}):
            result = rag_search("fractions")
        self.assertIn("Aucun document", result)
