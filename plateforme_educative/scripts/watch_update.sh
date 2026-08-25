#!/bin/bash
# Surveille un dossier de "mise à jour" sur la station. Dès qu'un fichier de
# backup (.tar.gz) y est déposé et complètement écrit, déclenche
# automatiquement la mise à jour du LMS via restore.sh.
#
# Le dossier de réception satellite/LAN (protocole FLUTE) qui réassemble les
# fragments de fichiers est un mécanisme séparé, hors scope du LMS : il doit
# simplement déposer le fichier final ici une fois reconstitué. Le LMS n'a
# pas à se soucier de la réception elle-même, seulement de réagir à
# l'arrivée du fichier complet.
#
# Usage : ./scripts/watch_update.sh [dossier_a_surveiller]
# Par défaut : ./updates/incoming

set -euo pipefail
cd "$(dirname "$0")/.."

WATCH_DIR="${1:-./updates/incoming}"
BASE_DIR="$(dirname "$WATCH_DIR")"
PROCESSED_DIR="$BASE_DIR/processed"
FAILED_DIR="$BASE_DIR/failed"
POLL_INTERVAL=5   # secondes entre deux vérifications du dossier
STABLE_CHECKS=3   # vérifications consécutives à taille identique avant de considérer le fichier complet

mkdir -p "$WATCH_DIR" "$PROCESSED_DIR" "$FAILED_DIR"

echo "Surveillance de : $WATCH_DIR"
echo "En attente d'un fichier de mise à jour (.tar.gz)..."

is_file_stable() {
  local file="$1"
  local previous_size current_size
  previous_size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo -1)
  [ "$previous_size" = "-1" ] && return 1

  for _ in $(seq 1 "$STABLE_CHECKS"); do
    sleep "$POLL_INTERVAL"
    current_size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo -1)
    if [ "$current_size" = "-1" ] || [ "$current_size" != "$previous_size" ]; then
      return 1
    fi
    previous_size="$current_size"
  done
  return 0
}

while true; do
  for FILE in "$WATCH_DIR"/*.tar.gz; do
    [ -e "$FILE" ] || continue

    echo ""
    echo "Fichier détecté : $FILE"
    echo "Vérification que le fichier est complètement écrit..."

    if is_file_stable "$FILE"; then
      echo "Fichier stable, déclenchement de la mise à jour du LMS..."
      if ./scripts/restore.sh "$FILE"; then
        mv "$FILE" "$PROCESSED_DIR/"
        echo "Mise à jour terminée avec succès. Fichier archivé dans $PROCESSED_DIR/"
      else
        mv "$FILE" "$FAILED_DIR/"
        echo "Échec de la mise à jour. Fichier déplacé dans $FAILED_DIR/ pour investigation." >&2
      fi
    else
      echo "Fichier encore en cours d'écriture, nouvelle vérification au prochain cycle."
    fi
  done
  sleep "$POLL_INTERVAL"
done
