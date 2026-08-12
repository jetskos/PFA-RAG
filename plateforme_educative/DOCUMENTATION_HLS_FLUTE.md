# 📡 Documentation Technique : Intégration HLS, Checksums & FLUTE

Ce document récapitule toutes les améliorations apportées à l'infrastructure d'import/export de cours et de traitement vidéo pour assurer la compatibilité avec le système de transmission par satellite (Projet FLUTE).

## 1. Sécurisation des transferts (Checksums SHA-256)
Afin de garantir qu'aucun fichier ne soit corrompu pendant le transfert par satellite (ou clé USB), un système de hachage cryptographique a été mis en place.
- **À l'export (`export_course_task`)** : Le LMS génère une empreinte numérique (hash SHA-256) pour chaque fichier physique (MP4, PDF, Images, et fichiers HLS). Ces hashs sont stockés dans la nouvelle section `"checksums"` du fichier `course_metadata.json`.
- **À l'import (`import_courses_task`)** : Avant de sauvegarder le moindre fichier en base de données, le LMS recalcule le hash du fichier reçu. Si l'empreinte diffère, l'importation est bloquée (statut `FAILED`) avec un message "Fichier corrompu", évitant ainsi d'insérer des données partielles.

## 2. Découpage Vidéo Optimisé (FFmpeg)
La tâche Celery de conversion vidéo (`convertir_video_hls`) a été reconfigurée pour respecter strictement la politique de nommage demandée par l'encadrant pour la transmission FLUTE :
- **Playlist principale** : Renommée spécifiquement en `Playlist.m3u8`.
- **Découpage (Chunks)** : Les segments sont découpés en morceaux de 10 secondes (`-hls_time 10`).
- **Nommage des segments** : L'argument `-hls_segment_filename` a été ajouté pour nommer les morceaux selon le format `Chunk_000.ts`, `Chunk_001.ts`...

## 3. Compatibilité avec l'outil de transmission "FLUTE"
Pour optimiser les ressources des serveurs hors-ligne (récepteurs) et permettre une lecture vidéo immédiate, le système d'export a été lourdement amélioré :
- **Exportation HLS Native** : Lorsqu'un cours est exporté, le LMS ne se contente plus d'inclure le fichier `.mp4` brut. Il embarque automatiquement **tout le dossier HLS complet** (la playlist et tous les chunks) à l'intérieur du ZIP final (`cours_export.zip`).
- **Importation Intelligente (Bypass FFmpeg)** : Lors de la réception de ce ZIP sur l'ordinateur cible, l'outil d'importation détecte la présence du dossier HLS. Après avoir validé les checksums des `.ts`, le LMS copie les fichiers HLS directement dans le dossier `media` du serveur et **annule le lancement de la conversion FFmpeg locale**. 
*Bénéfice : Le processeur du serveur récepteur n'a plus besoin de réencoder la vidéo, elle est immédiatement disponible au format HLS pour les étudiants !*

## 4. Correction de l'indexation lors des imports ZIP
Un bug empêchait le déclenchement de la conversion HLS et de l'indexation IA lorsque les cours étaient importés via un fichier ZIP (au lieu d'être créés manuellement via l'interface web).
- **Correctif** : L'appel aux tâches asynchrones (`convertir_video_hls.delay()` et `indexer_document_task.delay()`) a été rajouté directement à la fin du traitement du ZIP dans `import_courses_task`.
