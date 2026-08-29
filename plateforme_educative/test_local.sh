#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Test rapide, local, sans MySQL — vérifie la branche finalisation-plateforme
# sur une base SQLite jetable + un jeu de données de démo.
#
#   bash test_local.sh
#
# Serveur : http://127.0.0.1:8000   (admin@test.local / test1234)
# Ctrl+C pour arrêter. La base de test est supprimée à chaque relance.
# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

export DJANGO_SETTINGS_MODULE=core.settings
export DB_ENGINE=django.db.backends.sqlite3
# SQLite refuse les chemins avec accents/espaces (dossier OneDrive) -> base hors du projet
export DB_NAME="${LOCALAPPDATA:-$HOME}/pfarag_test_local.sqlite3"
export DJANGO_DEBUG=True
export PYTHONUTF8=1
export CELERY_TASK_ALWAYS_EAGER=True          # import de cours synchrone (pas besoin de Celery)
export CELERY_TASK_EAGER_PROPAGATES=True

rm -f "$DB_NAME"

echo "▶ Migrations…"
python manage.py migrate --noinput 2>&1 | tail -2

echo "▶ Traductions…"
python manage.py compilemessages -l en -l fr 2>&1 | grep -viE 'processing|up to date' || true

echo "▶ Données de démo (cours FR + cours EN)…"
python manage.py seed_demo 2>&1 | tail -2 || true
python manage.py seed_english_course 2>&1 | tail -1 || true

echo "▶ Compte admin de test…"
python manage.py shell -c "
from accounts.models import Utilisateur
u,_ = Utilisateur.objects.get_or_create(email='admin@test.local', defaults={'role':'ADMIN'})
u.set_password('test1234'); u.role='ADMIN'; u.is_superuser=True; u.is_staff=True
u.is_active=True; u.statut_compte='ACTIF'; u.save()
print('  admin@test.local / test1234')
"

echo "▶ Boîte satellite de démo (2 cours + 1 fichier corrompu + manifeste)…"
python - <<'PY'
import django; django.setup()
import hashlib, io, json, zipfile
from pathlib import Path
from django.conf import settings
inbox = Path(settings.SATELLITE_INBOX_DIR); inbox.mkdir(parents=True, exist_ok=True)
for p in inbox.glob('*'):
    if p.is_file(): p.unlink()

def course_zip(titre, chapitres):
    meta = {"version":"1.0","cours":{"titre":titre,"description":"Reçu par satellite.","resume":"","niveau":"NA"},
            "chapitres":[{"titre":c,"description":"","ordre":i+1,"url_video":"","documents":[]} for i,c in enumerate(chapitres)],
            "checksums":{}}
    b = io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('course_metadata.json', json.dumps(meta, ensure_ascii=False))
    return b.getvalue()

files = {
  'cours_robotique_export.zip': course_zip("Robotique Avancée (satellite)", ["Intro","Capteurs","Actionneurs"]),
  'cours_reseaux_export.zip':    course_zip("Réseaux LPWAN (satellite)", ["LoRaWAN","NB-IoT"]),
  'cours_corrompu_export.zip':   course_zip("Cours corrompu", ["X"]),
}
for name, data in files.items():
    (inbox/name).write_bytes(data)

def h(d): return hashlib.sha256(d).hexdigest()
man = ['<?xml version="1.0" encoding="utf-8"?>',
       '<manifest timestamp="1782163640" schema_version="2" cycle_id="42">']
for i,(name,data) in enumerate(files.items(),1):
    hh = '0'*64 if name=='cours_corrompu_export.zip' else h(data)   # empreinte fausse -> doit être signalée
    man.append(f'<file logical_name="{name}" original_size="{len(data)}" original_hash="{hh}" '
               f'mime_type="application/zip" order="{i}" zipped="false" artifact_name="{i:04d}_{name}" '
               f'artifact_size="{len(data)}" artifact_hash="{hh}" artifact_chunks="1" />')
man.append('</manifest>')
(inbox/'__MANIFEST__.xml').write_text(''.join(man), encoding='utf-8')
print('  déposé dans', inbox)
PY

# IP LAN de ce PC (pour tester depuis un téléphone sur le même Wi-Fi).
# Astuce socket : ne transmet rien, choisit juste l'interface de routage — marche hors-ligne.
LAN_IP=$(python -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('10.255.255.255',1)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "IP-de-ce-PC")

echo
echo "═══════════════════════════════════════════════════════════════════"
echo "  Sur ce PC     : http://127.0.0.1:8000/"
echo "  Sur téléphone : http://${LAN_IP}:8000/   (même Wi-Fi + pare-feu autorisé)"
echo "  Login         : admin@test.local / test1234"
echo "  PWA (install/hors-ligne) : 2e terminal → python serve_https.py"
echo "                             puis https://${LAN_IP}:8443/ sur le téléphone"
echo "═══════════════════════════════════════════════════════════════════"
# 0.0.0.0 = écoute sur toutes les interfaces (indispensable pour l'accès téléphone).
python manage.py runserver 0.0.0.0:8000
