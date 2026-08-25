#!/bin/bash
# Restauration complète de la plateforme à partir d'une archive créée par
# backup.sh : efface la base de données et les fichiers media existants,
# puis réinjecte tout automatiquement (base de données + classes/cours +
# chroma_db) et relance les services.
#
# Usage : ./scripts/restore.sh <chemin_vers_backup.tar.gz>

set -euo pipefail
cd "$(dirname "$0")/.."

ARCHIVE="${1:?Usage: ./scripts/restore.sh <backup.tar.gz>}"
ENV_FILE="${ENV_FILE:-.env.docker}"

if [ ! -f "$ARCHIVE" ]; then
  echo "Archive introuvable : $ARCHIVE" >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Fichier d'environnement introuvable : $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

echo "[1/7] Extraction de l'archive..."
tar -xzf "$ARCHIVE" -C "$WORKDIR"

echo "[2/7] Démarrage des services de base (db, redis)..."
docker compose up -d db redis

echo "[3/7] Attente que MySQL soit prêt..."
until docker compose exec -T db mysqladmin ping -uroot -p"${DB_PASSWORD}" --silent >/dev/null 2>&1; do
  echo "  ... MySQL n'est pas encore prêt, nouvelle tentative dans 2s"
  sleep 2
done

echo "[4/7] Réinitialisation de la base de données (${DB_NAME})..."
docker compose exec -T db mysql -uroot -p"${DB_PASSWORD}" -e \
  "DROP DATABASE IF EXISTS \`${DB_NAME}\`; CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4;"

echo "[5/7] Restauration du dump SQL..."
docker compose exec -T db mysql -uroot -p"${DB_PASSWORD}" "${DB_NAME}" < "$WORKDIR/db.sql"

echo "[6/7] Restauration des fichiers media (écrase l'existant)..."
rm -rf ./media
mv "$WORKDIR/media" ./media

echo ""
echo "Redémarrage complet de la plateforme (web + celery)..."
docker compose up -d --build

echo "[7/7] Vérification post-restauration..."
count_table() {
  # $1 = nom de table, en tolérant son absence (schéma différent selon la version)
  docker compose exec -T db mysql -N -uroot -p"${DB_PASSWORD}" "${DB_NAME}" \
    -e "SELECT COUNT(*) FROM \`$1\`;" 2>/dev/null || echo "n/a"
}
count_files() {
  # $1 = sous-dossier de media/
  [ -d "./media/$1" ] && find "./media/$1" -type f | wc -l || echo 0
}

echo ""
echo "=== Rapport de vérification ==="
echo "Base de données (${DB_NAME}) :"
echo "  - Utilisateurs (accounts_utilisateur) : $(count_table accounts_utilisateur)"
echo "  - Classes (accounts_classe)           : $(count_table accounts_classe)"
echo "  - Cours (apprentissage_cours)         : $(count_table apprentissage_cours)"
echo "  - Chapitres (apprentissage_chapitre)  : $(count_table apprentissage_chapitre)"
echo "  - Documents (apprentissage_document)  : $(count_table apprentissage_document)"
echo ""
echo "Fichiers media :"
echo "  - documents/    : $(count_files documents) fichier(s)"
echo "  - videos/       : $(count_files videos) fichier(s)"
echo "  - cours_covers/ : $(count_files cours_covers) fichier(s)"
echo "  - chroma_db/    : $(count_files chroma_db) fichier(s)"
echo "================================"
echo ""
echo "Restauration terminée : base '${DB_NAME}' et fichiers media rétablis."
