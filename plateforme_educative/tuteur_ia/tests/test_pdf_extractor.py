"""
Tests — nettoyage des artefacts d'extraction PDF (pdf_extractor._degarble).

Run : python manage.py test tuteur_ia.tests.test_pdf_extractor
"""
from django.test import SimpleTestCase

from tuteur_ia.tools.pdf_extractor import _degarble, _dedouble_word, clean_text


class DedoubleWordTest(SimpleTestCase):

    def test_repare_faux_gras(self):
        self.assertEqual(_dedouble_word("WWoorrkksshheeeett"), "Worksheet")
        self.assertEqual(_dedouble_word("PPrraaccttiiccee"), "Practice")

    def test_laisse_les_mots_normaux(self):
        for mot in ("Worksheet", "communiquer", "committee", "bookkeeper",
                    "possible", "accès", "toto", "papa"):
            self.assertEqual(_dedouble_word(mot), mot)

    def test_ignore_longueur_impaire_et_non_alpha(self):
        self.assertEqual(_dedouble_word("aaa"), "aaa")
        self.assertEqual(_dedouble_word("11"), "11")
        self.assertEqual(_dedouble_word("WWoorrkksshheeeett,"), "WWoorrkksshheeeett,")


class DegarbleTest(SimpleTestCase):

    def test_supprime_les_cid(self):
        self.assertEqual(_degarble("Name (cid:1)(cid:1) Score"), "Name  Score")

    def test_supprime_les_caracteres_de_controle(self):
        self.assertEqual(_degarble("abc\x00\x07def"), "abcdef")
        self.assertEqual(_degarble("ligne1\nligne2\tfin"), "ligne1\nligne2\tfin")

    def test_phrase_faux_gras_complete(self):
        brut = "PPrraaccttiiccee WWoorrkksshheeeett"
        self.assertEqual(_degarble(brut), "Practice Worksheet")

    def test_idempotent_sur_texte_propre(self):
        propre = "Read the questions carefully and do your best — I'm here if you need help!"
        self.assertEqual(_degarble(propre), propre)

    def test_clean_text_integre_le_degarblage(self):
        brut = "TTiittllee (cid:3)\n\n\nCorps de texte normal."
        out = clean_text(brut)
        self.assertIn("Title", out)
        self.assertNotIn("(cid:", out)
        self.assertNotIn("TTiittllee", out)
