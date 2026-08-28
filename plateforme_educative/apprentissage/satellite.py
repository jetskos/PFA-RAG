"""Détection et application des mises à jour de cours reçues par satellite.

Le récepteur du carrousel FLUTE (`carrousel_client.py --output <SATELLITE_INBOX_DIR>`)
dépose dans ce dossier les fichiers reçus, nommés par leur nom d'origine, ainsi qu'un
`__MANIFEST__.xml` décrivant le cycle courant. Ce module :

  1. scanne le dossier, repère les ZIP qui sont des exports de cours de la plateforme
     (présence de `course_metadata.json`) ;
  2. vérifie leur intégrité contre l'empreinte du manifeste quand elle est disponible ;
  3. crée/rafraîchit des lignes `SatelliteUpdate` (dédup par empreinte SHA-256) ;
  4. sur demande d'un administrateur, copie le ZIP hors du dossier miroir du récepteur
     et lance la tâche d'import asynchrone existante (`import_courses_task`).

Le récepteur FLUTE **supprime** de son dossier de sortie tout fichier absent du
manifeste courant : on ne consomme donc jamais le fichier sur place, on en fait
toujours une copie de travail.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

MANIFEST_NAME = '__MANIFEST__.xml'
PROCESSED_DIRNAME = 'processed'
_READ_BLOCK = 1024 * 1024


def get_inbox_dir() -> Path:
    """Retourne le dossier de réception satellite (créé si absent)."""
    path = Path(settings.SATELLITE_INBOX_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(_READ_BLOCK), b''):
            digest.update(block)
    return digest.hexdigest()


def _inspect_course_zip(path: Path) -> tuple[bool, str]:
    """(True, titre) si le ZIP est un export de cours de la plateforme, sinon (False, '')."""
    try:
        with zipfile.ZipFile(path) as archive:
            if 'course_metadata.json' not in archive.namelist():
                return False, ''
            with archive.open('course_metadata.json') as meta_file:
                metadata = json.load(meta_file)
        titre = str(metadata.get('cours', {}).get('titre', '')).strip()
        return True, titre[:255]
    except (zipfile.BadZipFile, OSError, ValueError, KeyError):
        return False, ''


def _read_manifest(inbox: Path) -> dict:
    """logical_name -> {'hash': <sha256 attendu>, 'cycle': <int|None>} depuis __MANIFEST__.xml."""
    manifest_path = inbox / MANIFEST_NAME
    if not manifest_path.exists():
        return {}
    try:
        root = ET.fromstring(manifest_path.read_bytes())
    except ET.ParseError:
        return {}
    raw_cycle = root.get('cycle_id')
    cycle = int(raw_cycle) if raw_cycle and raw_cycle.isdigit() else None
    entries: dict = {}
    for node in root.findall('file'):
        name = node.get('logical_name') or node.get('name') or ''
        if not name:
            continue
        entries[name] = {
            'hash': node.get('original_hash') or node.get('hash') or '',
            'cycle': cycle,
        }
    return entries


def scan_inbox():
    """Scanne la boîte de réception et met à jour les `SatelliteUpdate`.

    Retourne le queryset des mises à jour au statut ``DETECTED`` prêtes à être appliquées.
    """
    from django.db import IntegrityError
    from .models import SatelliteUpdate

    inbox = get_inbox_dir()
    (inbox / PROCESSED_DIRNAME).mkdir(exist_ok=True)
    manifest = _read_manifest(inbox)

    for entry in sorted(inbox.iterdir()):
        if entry.is_dir() or entry.suffix.lower() != '.zip':
            continue

        size = entry.stat().st_size

        # Fichier déjà connu (même nom + même taille) : on évite de re-hasher un gros ZIP.
        known = (
            SatelliteUpdate.objects
            .filter(logical_name=entry.name, size=size)
            .exclude(status='FAILED')
            .exists()
        )
        if known:
            continue

        file_hash = _sha256(entry)
        if SatelliteUpdate.objects.filter(file_hash=file_hash).exists():
            continue

        manifest_entry = manifest.get(entry.name) or {}
        expected_hash = manifest_entry.get('hash') or ''
        cycle_id = manifest_entry.get('cycle')

        if expected_hash and expected_hash != file_hash:
            defaults = {
                'logical_name': entry.name, 'size': size, 'cycle_id': cycle_id,
                'status': 'FAILED',
                'erreur': _("Empreinte différente du manifeste satellite (fichier corrompu ou incomplet)."),
            }
        else:
            is_course, titre = _inspect_course_zip(entry)
            if not is_course:
                continue  # ZIP quelconque : hors périmètre, on l'ignore silencieusement.
            defaults = {
                'logical_name': entry.name, 'size': size, 'cycle_id': cycle_id,
                'titre_cours': titre, 'status': 'DETECTED',
            }

        try:
            SatelliteUpdate.objects.get_or_create(file_hash=file_hash, defaults=defaults)
        except IntegrityError:
            pass  # course créé en parallèle par un autre scan concurrent

    return SatelliteUpdate.objects.filter(status='DETECTED')


def reconcile_statuses() -> None:
    """Aligne les `SatelliteUpdate` en cours d'import sur l'état réel de leur `ImportJob`."""
    from .models import SatelliteUpdate

    running = SatelliteUpdate.objects.filter(status='IMPORTING').select_related('import_job')
    for update in running:
        job = update.import_job
        if job is None:
            continue
        if job.status == 'TERMINE':
            update.status = 'APPLIED'
            if job.titre_cours:
                update.titre_cours = job.titre_cours[:255]
            update.save(update_fields=['status', 'titre_cours'])
        elif job.status == 'FAILED':
            update.status = 'FAILED'
            update.erreur = job.erreur or _("Import échoué.")
            update.save(update_fields=['status', 'erreur'])


def apply_update(update, user):
    """Copie le ZIP hors du dossier miroir du récepteur et lance l'import asynchrone.

    Transition de statut atomique : si la mise à jour n'est plus ``DETECTED``
    (déjà lancée par un autre administrateur), on ne fait rien.
    """
    from .models import ImportJob, SatelliteUpdate
    from .tasks import import_courses_task

    claimed = SatelliteUpdate.objects.filter(pk=update.pk, status='DETECTED').update(status='IMPORTING')
    if not claimed:
        update.refresh_from_db()
        return update

    inbox = get_inbox_dir()
    source = inbox / update.logical_name

    if not source.exists():
        SatelliteUpdate.objects.filter(pk=update.pk).update(
            status='FAILED',
            erreur=_("Le fichier a été retiré de la boîte de réception satellite avant son application."),
        )
        update.refresh_from_db()
        return update

    # `import_courses_task` supprime le fichier qu'on lui passe : on travaille sur une copie.
    work_dir = Path(settings.MEDIA_ROOT) / 'imports' / 'temp'
    work_dir.mkdir(parents=True, exist_ok=True)
    work_path = work_dir / f"sat_{uuid.uuid4().hex}_{update.logical_name}"
    shutil.copy2(source, work_path)

    job = ImportJob.objects.create(formateur=user)
    update.import_job = job
    update.status = 'IMPORTING'
    update.applied_by = user
    update.applied_at = timezone.now()
    update.save(update_fields=['import_job', 'status', 'applied_by', 'applied_at'])

    import_courses_task.delay(str(job.id), user.id, [str(work_path)])

    # Archive l'original pour ne plus le re-détecter (sans le retirer du dossier du récepteur).
    processed = inbox / PROCESSED_DIRNAME
    processed.mkdir(exist_ok=True)
    try:
        shutil.copy2(source, processed / update.logical_name)
    except OSError:
        pass

    return update
