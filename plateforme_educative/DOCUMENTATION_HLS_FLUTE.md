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

---

## 5. Import automatisé depuis le satellite (bouton "Mises à jour" du tableau de bord)

Le carrousel FLUTE (`FLUTE_Send--Receive_Project`, projet Python autonome de l'encadrant) est
la **couche de transport** : l'émetteur diffuse en UDP multicast, le récepteur
(`carrousel_client.py --output <dossier>`) reconstruit les fichiers et vérifie leur
empreinte SHA-256.

### Câblage

1. Sur le serveur hors-ligne (VM 101), lancer le récepteur du carrousel **en service**
   (redémarre tout seul, démarre au boot), sa sortie pointée sur la **boîte de
   réception** de la plateforme :
   ```bash
   sudo cp plateforme_educative/deploy/flute-receiver.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now flute-receiver
   journalctl -u flute-receiver -f
   ```
   Adapter dans le fichier `.service` : `User`, `WorkingDirectory`, et surtout
   `--output` qui **doit valoir `SATELLITE_INBOX_DIR`** du `.env` de la plateforme
   (défaut : `<projet>/media/satellite_inbox`).
   Lancement manuel équivalent pour un test :
   ```bash
   python carrousel_client.py --output <SATELLITE_INBOX_DIR>
   ```

2. L'encadrant diffuse depuis son poste les **ZIP d'export de cours** produits par la
   plateforme (`cours_<id>_export.zip`, onglet *Espace formateur → Exporter*).

### Côté plateforme

- Le tableau de bord admin (`/dashboard/admin/`) affiche une carte **« N mises à jour reçues
  par satellite »** dès qu'un ZIP d'export de cours valide est présent dans la boîte.
  La carte se rafraîchit toute seule (HTMX, toutes les 30 s).
- La détection (`apprentissage/satellite.py → scan_inbox`) :
  - ne retient que les ZIP contenant un `course_metadata.json` (les autres fichiers du
    carrousel sont ignorés) ;
  - vérifie l'empreinte contre le `__MANIFEST__.xml` du carrousel quand il est présent
    (statut `FAILED` + message si le fichier est corrompu) ;
  - déduplique par empreinte SHA-256 (un cours déjà appliqué n'est pas re-proposé).
- Le responsable clique **« Appliquer »** (par cours) ou **« Tout appliquer »**. Chaque
  mise à jour :
  - est copiée hors du dossier du récepteur (qui purge les fichiers absents du cycle
    courant), puis passée à la tâche existante `import_courses_task` ;
  - est archivée dans `media/satellite_inbox/processed/` ;
  - suit son `ImportJob` ; le statut passe `DETECTED → IMPORTING → APPLIED` (ou `FAILED`).
- Suivi et historique dans l'admin Django (`Apprentissage → Mises à jour satellite`).

> Le fichier d'origine **n'est jamais supprimé** de la boîte de réception : c'est le
> récepteur FLUTE qui gère ce dossier comme un miroir de son dernier cycle.
