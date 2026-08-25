#!/bin/bash
# Sauvegarde complète de la plateforme : dump MySQL + fichiers media (dont
# chroma_db, la base vectorielle du tuteur IA) dans une seule archive.
#
# Usage : ./scripts/backup.sh [dossier_de_sortie]
# Par défaut, l'archive est écrite dans ./backups/backup_<date>.tar.gz
#
# L'archive produite est le fichier à "injecter" sur un autre serveur via
# restore.sh pour rétablir automatiquement la base de données et les classes.

set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-./backups}"
ENV_FILE="${ENV_FILE:-.env.docker}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ ! -f "$ENV_FILE" ]; then
  echo "Fichier d'environnement introuvable : $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

mkdir -p "$OUT_DIR"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

echo "[1/3] Dump de la base de données MySQL (${DB_NAME})..."
docker compose exec -T db mysqldump \
  -uroot -p"${DB_PASSWORD}" \
  --single-transaction --routines --triggers \
  "${DB_NAME}" > "$WORKDIR/db.sql"

echo "[2/3] Copie des fichiers media (documents, vidéos, chroma_db, imports)..."
mkdir -p "$WORKDIR/media"
if [ -d "./media" ]; then
  cp -r ./media/. "$WORKDIR/media/"
fi

echo "[3/3] Création de l'archive..."
ARCHIVE="$OUT_DIR/backup_${TIMESTAMP}.tar.gz"
tar -czf "$ARCHIVE" -C "$WORKDIR" db.sql media

echo ""
echo "Backup créé : $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
