"""
Tâches Celery pour le module apprentissage.
- indexer_document_task : indexation asynchrone d'un PDF dans ChromaDB
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30,
             name='apprentissage.tasks.indexer_document_task')
def indexer_document_task(self, document_id: str, pdf_path: str):
    """
    Extrait le texte d'un PDF et l'indexe dans ChromaDB de manière asynchrone.

    Args:
        document_id : UUID du Document en base de données.
        pdf_path    : Chemin absolu vers le fichier PDF sur le disque.
    """
    logger.info(f"[ChromaDB] Indexation démarrée — doc {document_id[:8]}...")
    print(f"\n[🚀 ChromaDB] Démarrage de l'indexation pour le document {document_id[:8]}...")
    try:
        from apprentissage.models import Document
        from tuteur_ia.tools.pdf_extractor import extract_and_chunk_pdf
        from tuteur_ia.tools.chroma_store import add_chunks

        # 1. Extraire et chunker le PDF
        full_text, chunks = extract_and_chunk_pdf(pdf_path)

        if not full_text:
            logger.warning(f"[ChromaDB] PDF vide ou scanné : {pdf_path}")
            return

        # 2. Mettre à jour contenu_extrait en base
        Document.objects.filter(pk=document_id).update(contenu_extrait=full_text)

        # 3. Récupérer métadonnées pour les filtres ChromaDB
        doc = Document.objects.get(pk=document_id)

        # 4. Indexer dans ChromaDB (remplace les anciens chunks si existants)
        add_chunks(
            chunks=chunks,
            document_id=document_id,
            document_titre=doc.titre,
            chapitre_id=str(doc.chapitre_id),
            cours_id=str(doc.chapitre.cours_id),
        )

        logger.info(
            f"[ChromaDB] ✓ '{doc.titre}' indexé : "
            f"{len(full_text):,} chars, {len(chunks)} chunks"
        )

    except Exception as exc:
        logger.error(
            f"[ChromaDB] ✗ Erreur indexation {document_id}: {exc}",
            exc_info=True,
        )

import json
import zipfile
import shutil
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from .models import ExportJob, Cours
import hashlib

def calculate_checksum(file_path):
    """Calcule le hash SHA-256 d'un fichier."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@shared_task(bind=True, max_retries=1, name='apprentissage.tasks.export_course_task')
def export_course_task(self, export_job_id: str):
    logger.info(f"[Export] Démarrage de la tâche pour le job {export_job_id}")
    print(f"\n[📦 Export] Démarrage de l'exportation du cours (Job: {export_job_id})")
    try:
        job = ExportJob.objects.get(pk=export_job_id)
        cours = job.cours
        
        # 1. Préparation du répertoire temporaire
        base_export_dir = Path(settings.MEDIA_ROOT) / 'exports' / 'temp' / str(job.id)
        base_export_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Construction des métadonnées
        metadata = {
            'version': '1.0',
            'cours': {
                'titre': cours.titre,
                'description': cours.description,
                'resume': cours.resume,
                'niveau': cours.niveau.code,
            },
            'chapitres': [],
            'checksums': {}
        }
        
        if cours.image_couverture:
            img_path = Path(cours.image_couverture.path)
            if img_path.exists():
                shutil.copy2(img_path, base_export_dir / img_path.name)
                metadata['cours']['image_couverture'] = img_path.name
                metadata['checksums'][img_path.name] = calculate_checksum(img_path)

        for chapitre in cours.chapitres.all():
            chap_data = {
                'titre': chapitre.titre,
                'description': chapitre.description,
                'ordre': chapitre.ordre,
                'url_video': chapitre.url_video,
                'documents': []
            }
            
            if chapitre.video_fichier:
                vid_path = Path(chapitre.video_fichier.path)
                if vid_path.exists():
                    shutil.copy2(vid_path, base_export_dir / vid_path.name)
                    chap_data['video_fichier'] = vid_path.name
                    metadata['checksums'][vid_path.name] = calculate_checksum(vid_path)
                    
            if getattr(chapitre, 'is_hls_ready', False) and chapitre.video_hls_url:
                hls_rel_path = Path(chapitre.video_hls_url)
                hls_abs_path = Path(settings.MEDIA_ROOT) / hls_rel_path
                hls_dir = hls_abs_path.parent
                if hls_dir.exists() and hls_dir.is_dir():
                    dest_hls_dir = base_export_dir / hls_dir.name
                    if not dest_hls_dir.exists():
                        shutil.copytree(hls_dir, dest_hls_dir)
                    chap_data['video_hls_dir'] = hls_dir.name
                    chap_data['video_hls_playlist'] = hls_abs_path.name
                    for hls_file in dest_hls_dir.rglob('*'):
                        if hls_file.is_file():
                            rel_name = f"{hls_dir.name}/{hls_file.name}"
                            metadata['checksums'][rel_name] = calculate_checksum(hls_file)
                    
            for doc in chapitre.documents.filter(actif=True):
                if doc.fichier_pdf:
                    doc_path = Path(doc.fichier_pdf.path)
                    if doc_path.exists():
                        shutil.copy2(doc_path, base_export_dir / doc_path.name)
                        chap_data['documents'].append({
                            'titre': doc.titre,
                            'type_document': doc.type_document,
                            'description': doc.description,
                            'ordre': doc.ordre,
                            'fichier_pdf': doc_path.name
                        })
                        metadata['checksums'][doc_path.name] = calculate_checksum(doc_path)
            metadata['chapitres'].append(chap_data)

        # 3. Sauvegarder le JSON
        with open(base_export_dir / 'course_metadata.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

        # 4. Créer le fichier ZIP
        zip_filename = f'cours_{cours.id}_export.zip'
        zip_filepath = Path(settings.MEDIA_ROOT) / 'exports' / 'cours' / str(timezone.now().year) / str(timezone.now().month)
        zip_filepath.mkdir(parents=True, exist_ok=True)
        final_zip_path = zip_filepath / zip_filename

        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in base_export_dir.rglob('*'):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(base_export_dir))

        # 5. Nettoyer le dossier temporaire
        shutil.rmtree(base_export_dir, ignore_errors=True)

        # 6. Mettre à jour le statut
        rel_zip_path = str(final_zip_path.relative_to(settings.MEDIA_ROOT)).replace('\\\\', '/')
        job.fichier_zip.name = rel_zip_path
        job.status = 'SUCCESS'
        job.date_fin = timezone.now()
        job.save()

        logger.info(f"[Export] Succès pour le job {export_job_id}")
        print(f"[✅ Export] Exportation terminée avec succès ! (Fichier: {zip_filename})")

    except Exception as e:
        logger.error(f"[Export] Erreur pour le job {export_job_id}: {e}", exc_info=True)
        ExportJob.objects.filter(pk=export_job_id).update(
            status='FAILED',
            erreur=str(e),
            date_fin=timezone.now()
        )

import uuid

@shared_task(bind=True, name='apprentissage.tasks.import_courses_task')
def import_courses_task(self, import_job_id: str, user_id: str, zip_files: list):
    logger.info(f"[Import] Démarrage de l'importation (job {import_job_id}) de {len(zip_files)} fichier(s) par l'utilisateur {user_id}")
    print(f"\n[📥 Import] Démarrage de l'importation de {len(zip_files)} fichier(s) ZIP...")
    from apprentissage.models import ImportJob
    job = ImportJob.objects.filter(pk=import_job_id).first()
    if job:
        job.status = 'EXTRACTION'
        job.save()
    try:
        from accounts.models import Utilisateur
        from apprentissage.models import Niveau, Cours, Chapitre, Document, ImportJob
        from django.core.files import File
        
        job = ImportJob.objects.get(pk=import_job_id)
        user = Utilisateur.objects.get(pk=user_id)
        imported_cours_titres = []
        
        job.status = 'EXTRACTION'
        job.save()
        
        docs_to_index = []
        
        for zip_path_str in zip_files:
            zip_path = Path(zip_path_str)
            if not zip_path.exists():
                continue
                
            extract_dir = Path(settings.MEDIA_ROOT) / 'imports' / 'temp' / str(uuid.uuid4())
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(extract_dir)
                    
                meta_file = extract_dir / 'course_metadata.json'
                if not meta_file.exists():
                    continue
                    
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    
                checksums = metadata.get('checksums', {})
                def verify_file(file_path, filename):
                    expected_hash = checksums.get(filename)
                    if expected_hash:
                        actual_hash = calculate_checksum(file_path)
                        if actual_hash != expected_hash:
                            raise ValueError(f"Fichier corrompu : {filename} (attendu {expected_hash}, obtenu {actual_hash})")
                    
                job.status = 'SAUVEGARDE_BDD'
                job.titre_cours = metadata.get('cours', {}).get('titre', 'Cours importé')
                job.save()
                    
                c_data = metadata.get('cours', {})
                niveau_code = c_data.get('niveau') or "NA"
                niveau, _ = Niveau.objects.get_or_create(code=niveau_code, defaults={'nom': niveau_code})
                
                cours_titre = f"{c_data.get('titre', 'Cours importé')} (Importé)"
                cours = Cours.objects.create(
                    titre=cours_titre,
                    description=c_data.get('description', ''),
                    resume=c_data.get('resume', ''),
                    niveau=niveau,
                    createur=user,
                    actif=True # Les cours importés sont directement actifs
                )
                imported_cours_titres.append(cours_titre)
                
                if 'image_couverture' in c_data:
                    img_file = extract_dir / c_data['image_couverture']
                    if img_file.exists():
                        verify_file(img_file, img_file.name)
                        with open(img_file, 'rb') as f:
                            cours.image_couverture.save(img_file.name, File(f))
                            
                for chap_data in metadata.get('chapitres', []):
                    chapitre = Chapitre.objects.create(
                        cours=cours,
                        titre=chap_data.get('titre', 'Chapitre sans titre'),
                        description=chap_data.get('description', ''),
                        ordre=chap_data.get('ordre', 0),
                        url_video=chap_data.get('url_video', '')
                    )
                    
                    if 'video_fichier' in chap_data:
                        vid_file = extract_dir / chap_data['video_fichier']
                        if vid_file.exists():
                            verify_file(vid_file, vid_file.name)
                            with open(vid_file, 'rb') as f:
                                chapitre.video_fichier.save(vid_file.name, File(f))
                                
                            # Si le dossier HLS est aussi fourni, on le restaure et on bypass la génération FFmpeg
                            if 'video_hls_dir' in chap_data and 'video_hls_playlist' in chap_data:
                                hls_src_dir = extract_dir / chap_data['video_hls_dir']
                                if hls_src_dir.exists() and hls_src_dir.is_dir():
                                    for hls_file in hls_src_dir.rglob('*'):
                                        if hls_file.is_file():
                                            rel_name = f"{chap_data['video_hls_dir']}/{hls_file.name}"
                                            verify_file(hls_file, rel_name)
                                    
                                    # Déplacer vers media/videos/hls/<uuid>
                                    dest_hls_dir = Path(settings.MEDIA_ROOT) / 'videos' / 'hls' / f"chap_{chapitre.id}_hls"
                                    dest_hls_dir.mkdir(parents=True, exist_ok=True)
                                    
                                    # Copier les fichiers
                                    for item in hls_src_dir.iterdir():
                                        if item.is_file():
                                            shutil.copy2(item, dest_hls_dir / item.name)
                                            
                                    chapitre.is_hls_ready = True
                                    rel_hls_path = str((dest_hls_dir / chap_data['video_hls_playlist']).relative_to(settings.MEDIA_ROOT)).replace('\\\\', '/').replace('\\', '/')
                                    chapitre.video_hls_url = rel_hls_path
                                    chapitre.save(update_fields=['is_hls_ready', 'video_hls_url'])
                            else:
                                convertir_video_hls.delay(str(chapitre.pk))
                                
                    for doc_data in chap_data.get('documents', []):
                        doc = Document.objects.create(
                            chapitre=chapitre,
                            titre=doc_data.get('titre', 'Document'),
                            type_document=doc_data.get('type_document', 'RESSOURCE'),
                            description=doc_data.get('description', ''),
                            ordre=doc_data.get('ordre', 0)
                        )
                        if 'fichier_pdf' in doc_data:
                            pdf_file = extract_dir / doc_data['fichier_pdf']
                            if pdf_file.exists():
                                verify_file(pdf_file, pdf_file.name)
                                with open(pdf_file, 'rb') as f:
                                    doc.fichier_pdf.save(pdf_file.name, File(f))
                                docs_to_index.append(doc)
                                    
            finally:
                # Cleanup
                shutil.rmtree(extract_dir, ignore_errors=True)
                if zip_path.exists():
                    zip_path.unlink()
        if job:
            if docs_to_index:
                job.status = 'INDEXATION_IA'
                job.save()
                for doc in docs_to_index:
                    indexer_document_task.delay(str(doc.id), doc.fichier_pdf.path)

            job.status = 'TERMINE'
            job.titre_cours = ", ".join(imported_cours_titres) if imported_cours_titres else "Cours importé"
            job.date_fin = timezone.now()
            job.save()

        logger.info(f"[Import] Fin de l'importation par l'utilisateur {user_id}")
        print(f"[✅ Import] Importation terminée avec succès ! ({', '.join(imported_cours_titres) if imported_cours_titres else 'Aucun cours'})")
    except Exception as e:
        logger.error(f"[Import] Erreur globale: {e}", exc_info=True)
        if job:
            job.status = 'FAILED'
            job.erreur = str(e)
            job.date_fin = timezone.now()
            job.save()

import subprocess

@shared_task(bind=True, name='apprentissage.tasks.convertir_video_hls')
def convertir_video_hls(self, chapitre_id: str):
    logger.info(f"[HLS] Démarrage de la conversion pour le chapitre {chapitre_id}")
    print(f"\n[🎬 HLS] Démarrage de l'encodage vidéo (Chapitre: {chapitre_id})...")
    try:
        from apprentissage.models import Chapitre
        chapitre = Chapitre.objects.get(pk=chapitre_id)
        
        if not chapitre.video_fichier:
            logger.warning(f"[HLS] Pas de vidéo pour le chapitre {chapitre_id}")
            return
            
        video_path = Path(chapitre.video_fichier.path)
        if not video_path.exists():
            logger.warning(f"[HLS] Fichier vidéo introuvable : {video_path}")
            return
            
        # Créer le répertoire de destination pour HLS
        # media/videos/YYYY/MM/nom_video_hls/
        hls_dir = video_path.parent / f"{video_path.stem}_hls"
        hls_dir.mkdir(parents=True, exist_ok=True)
        
        playlist_path = hls_dir / 'Playlist.m3u8'
        segment_path = hls_dir / 'Chunk_%03d.ts'
        
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            # Fallback in case Celery worker started before PATH was refreshed
            import os
            local_app_data = os.environ.get('LOCALAPPDATA', '')
            fallback = os.path.join(local_app_data, r"Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")
            if os.path.exists(fallback):
                ffmpeg_path = fallback
            else:
                ffmpeg_path = 'ffmpeg'

        # Commande FFmpeg pour générer le HLS (720p)
        cmd = [
            ffmpeg_path, '-y', '-i', str(video_path),
            '-profile:v', 'baseline', '-level', '3.0',
            '-s', '1280x720', '-start_number', '0',
            '-hls_time', '10', '-hls_list_size', '0',
            '-hls_segment_filename', str(segment_path),
            '-f', 'hls', str(playlist_path)
        ]
        
        logger.info(f"[HLS] Exécution de FFmpeg: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Mettre à jour le chapitre
        rel_hls_path = str(playlist_path.relative_to(settings.MEDIA_ROOT)).replace('\\\\', '/').replace('\\', '/')
        
        Chapitre.objects.filter(pk=chapitre_id).update(
            is_hls_ready=True,
            video_hls_url=rel_hls_path
        )
        
        logger.info(f"[HLS] Succès: Playlist générée à {rel_hls_path}")
        print(f"[✅ HLS] Conversion terminée avec succès ! (Playlist: {rel_hls_path})")
        
    except FileNotFoundError:
        logger.warning("[HLS] FFmpeg non installé sur le système. Conversion vidéo HLS ignorée.")
    except subprocess.CalledProcessError as e:
        logger.error(f"[HLS] Erreur FFmpeg: {e.stderr.decode('utf-8', errors='ignore')}")
    except Exception as e:
        logger.error(f"[HLS] Erreur inattendue: {e}", exc_info=True)

