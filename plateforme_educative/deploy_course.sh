#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Injecte un cours (ZIP d'export) dans le LMS — en une commande, sans souris.
#
#   bash deploy_course.sh cours.zip                     # ajoute le cours
#   bash deploy_course.sh cours.zip --replace-all       # efface TOUT puis injecte
#   bash deploy_course.sh cours.zip --replace "IoT"     # remplace le cours "IoT"
#   AS=prof@ecole.ma bash deploy_course.sh cours.zip    # choisit le propriétaire
#
# 100 % hors-ligne : aucun worker Celery requis, le ZIP source n'est pas modifié.
# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

ZIP="${1:-}"
shift || true
if [ ! -f "$ZIP" ]; then
  echo "Usage : bash deploy_course.sh <cours.zip> [--replace-all | --replace \"TITRE\"]"
  exit 1
fi

echo "== Migrations (au cas où le schéma serait en retard) =="
python manage.py migrate --noinput | tail -1

echo
echo "== Import du cours =="
EXTRA=()
[ -n "${AS:-}" ] && EXTRA+=(--as "$AS")
python manage.py import_course "$ZIP" "$@" "${EXTRA[@]}" -y

echo
echo "== Terminé. Recharge la page du catalogue pour voir le cours. =="
