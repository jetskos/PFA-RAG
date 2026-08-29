"""
Tests de l'import automatisé des mises à jour reçues par satellite
(module apprentissage.satellite + carte du tableau de bord admin).
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apprentissage.models import Cours, ImportJob, SatelliteUpdate

Utilisateur = get_user_model()


def _course_zip(titre="Cours satellite", niveau="NA", chapitres=("Chap 1",)):
    meta = {
        "version": "1.0",
        "cours": {"titre": titre, "description": "", "resume": "", "niveau": niveau},
        "chapitres": [
            {"titre": c, "description": "", "ordre": i + 1, "url_video": "", "documents": []}
            for i, c in enumerate(chapitres)
        ],
        "checksums": {},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("course_metadata.json", json.dumps(meta, ensure_ascii=False))
    return buf.getvalue()


def _plain_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.txt", "pas un export de cours")
    return buf.getvalue()


def _manifest(entries):
    """entries : list de (name, bytes, hash_override|None)"""
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<manifest timestamp="1" schema_version="2" cycle_id="7">']
    for i, (name, data, override) in enumerate(entries, 1):
        h = override or hashlib.sha256(data).hexdigest()
        parts.append(
            f'<file logical_name="{name}" original_size="{len(data)}" original_hash="{h}" '
            f'mime_type="application/zip" order="{i}" zipped="false" '
            f'artifact_name="{i:04d}_{name}" artifact_size="{len(data)}" '
            f'artifact_hash="{h}" artifact_chunks="1" />'
        )
    parts.append("</manifest>")
    return "".join(parts)


class SatelliteBase(TestCase):
    def setUp(self):
        self.tmp = Path(self._get_tmpdir())
        self.inbox = self.tmp / "satellite_inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.admin = Utilisateur.objects.create_superuser(email="admin@ex.com", password="pw")
        self.admin.role = "ADMIN"
        self.admin.save()
        self.prof = Utilisateur.objects.create_user(email="prof@ex.com", password="pw")
        self.prof.role = "FORMATEUR"
        self.prof.is_active = True
        self.prof.save()

    def _get_tmpdir(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="sat_test_")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    def _settings(self):
        return override_settings(SATELLITE_INBOX_DIR=str(self.inbox))

    def _write(self, name, data):
        (self.inbox / name).write_bytes(data)

    def _write_manifest(self, entries):
        (self.inbox / "__MANIFEST__.xml").write_text(_manifest(entries), encoding="utf-8")


class ScanInboxTests(SatelliteBase):
    def test_detects_course_zip_and_ignores_plain_zip(self):
        z1 = _course_zip("Robotique")
        z2 = _plain_zip()
        self._write("cours_robotique_export.zip", z1)
        self._write("autre.zip", z2)
        self._write_manifest([("cours_robotique_export.zip", z1, None),
                              ("autre.zip", z2, None)])
        with self._settings():
            from apprentissage.satellite import scan_inbox
            pending = list(scan_inbox())
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].logical_name, "cours_robotique_export.zip")
        self.assertEqual(pending[0].titre_cours, "Robotique")
        self.assertEqual(pending[0].cycle_id, 7)
        self.assertEqual(SatelliteUpdate.objects.filter(status="DETECTED").count(), 1)

    def test_corrupt_file_is_flagged_failed(self):
        z = _course_zip("Corrompu")
        self._write("cours_corrompu_export.zip", z)
        self._write_manifest([("cours_corrompu_export.zip", z, "0" * 64)])
        with self._settings():
            from apprentissage.satellite import scan_inbox
            list(scan_inbox())
        u = SatelliteUpdate.objects.get(logical_name="cours_corrompu_export.zip")
        self.assertEqual(u.status, "FAILED")
        self.assertIn("manifeste", u.erreur.lower())

    def test_scan_is_idempotent(self):
        z = _course_zip("Idempotent")
        self._write("cours_x_export.zip", z)
        self._write_manifest([("cours_x_export.zip", z, None)])
        with self._settings():
            from apprentissage.satellite import scan_inbox
            list(scan_inbox())
            list(scan_inbox())
            list(scan_inbox())
        self.assertEqual(SatelliteUpdate.objects.count(), 1)

    def test_works_without_manifest(self):
        z = _course_zip("Sans manifeste")
        self._write("cours_sm_export.zip", z)
        with self._settings():
            from apprentissage.satellite import scan_inbox
            pending = list(scan_inbox())
        self.assertEqual(len(pending), 1)
        self.assertIsNone(pending[0].cycle_id)


class ApplyUpdateTests(SatelliteBase):
    def test_apply_creates_import_job_and_archives(self):
        z = _course_zip("A appliquer", chapitres=("C1", "C2"))
        self._write("cours_apply_export.zip", z)
        self._write_manifest([("cours_apply_export.zip", z, None)])
        with self._settings():
            from apprentissage.satellite import scan_inbox, apply_update, reconcile_statuses
            u = scan_inbox().first()
            with self.settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True):
                apply_update(u, self.admin)
                reconcile_statuses()
            u.refresh_from_db()

        self.assertEqual(u.status, "APPLIED")
        self.assertIsNotNone(u.import_job_id)
        self.assertEqual(u.applied_by, self.admin)
        self.assertTrue(Cours.objects.filter(titre__icontains="A appliquer").exists())
        self.assertTrue((self.inbox / "processed" / "cours_apply_export.zip").exists())

    def test_double_apply_is_safe(self):
        z = _course_zip("Concurrence")
        self._write("cours_race_export.zip", z)
        self._write_manifest([("cours_race_export.zip", z, None)])
        with self._settings():
            from apprentissage.satellite import scan_inbox, apply_update
            u = scan_inbox().first()
            with self.settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True):
                apply_update(u, self.admin)
                stale = SatelliteUpdate.objects.get(pk=u.pk)   # copie « périmée »
                apply_update(stale, self.admin)
        self.assertEqual(ImportJob.objects.count(), 1)


class DashboardCardTests(SatelliteBase):
    def test_card_endpoint_admin_only(self):
        url = reverse("apprentissage:satellite_updates_card")
        with self._settings():
            self.client.force_login(self.prof)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_card_lists_pending_and_apply_all(self):
        z1 = _course_zip("Carte 1")
        z2 = _course_zip("Carte 2")
        self._write("cours_c1_export.zip", z1)
        self._write("cours_c2_export.zip", z2)
        self._write_manifest([("cours_c1_export.zip", z1, None),
                              ("cours_c2_export.zip", z2, None)])
        with self._settings(), self.settings(CELERY_TASK_ALWAYS_EAGER=True,
                                             CELERY_TASK_EAGER_PROPAGATES=True):
            self.client.force_login(self.admin)
            r = self.client.get(reverse("apprentissage:satellite_updates_card"))
            self.assertContains(r, "Carte 1")
            self.assertContains(r, "Carte 2")

            r = self.client.post(reverse("apprentissage:apply_all_satellite_updates"))
            self.assertEqual(r.status_code, 200)
        self.assertEqual(SatelliteUpdate.objects.filter(status__in=["IMPORTING", "APPLIED"]).count(), 2)
