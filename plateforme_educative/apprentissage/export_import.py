import json
import zipfile
import io
import os
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Cours, Chapitre, Document, Devoir
from accounts.models import Niveau

def export_cours_edutech(cours_id):
    """
    Exporte un cours et ses médias associés sous forme de fichier .edutech (ZIP).
    Retourne un objet io.BytesIO contenant le ZIP.
    """
    try:
        cours = Cours.objects.get(id=cours_id)
    except Cours.DoesNotExist:
        return None

    manifest = {
        "version": "1.0",
        "type": "edutech_cours",
        "cours": {
            "titre": cours.titre,
            "description": cours.description,
            "niveau_code": cours.niveau.code if cours.niveau else None,
            "resume": cours.resume,
            "actif": cours.actif,
            "image_couverture": None,
            "chapitres": []
        }
    }

    # Création du buffer ZIP en mémoire
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        
        # 1. Image de couverture
        if cours.image_couverture and cours.image_couverture.name:
            try:
                file_path = cours.image_couverture.path
                if os.path.exists(file_path):
                    arcname = f"media/covers/{os.path.basename(file_path)}"
                    zip_file.write(file_path, arcname)
                    manifest["cours"]["image_couverture"] = arcname
            except Exception as e:
                pass # Ignorer si le fichier n'existe pas physiquement

        # 2. Chapitres
        for chap in cours.chapitres.all():
            chap_data = {
                "titre": chap.titre,
                "description": chap.description,
                "ordre": chap.ordre,
                "url_video": chap.url_video,
                "fichier_video": None,
                "actif": chap.actif,
                "documents": [],
                "devoirs": []
            }
            
            if chap.fichier_video and chap.fichier_video.name:
                try:
                    file_path = chap.fichier_video.path
                    if os.path.exists(file_path):
                        arcname = f"media/videos/chapitres/{os.path.basename(file_path)}"
                        zip_file.write(file_path, arcname)
                        chap_data["fichier_video"] = arcname
                except Exception:
                    pass
            
            # Documents
            for doc in chap.documents.all():
                doc_data = {
                    "titre": doc.titre,
                    "type_document": doc.type_document,
                    "description": doc.description,
                    "ordre": doc.ordre,
                    "actif": doc.actif,
                    "fichier_pdf": None
                }
                if doc.fichier_pdf and doc.fichier_pdf.name:
                    try:
                        file_path = doc.fichier_pdf.path
                        if os.path.exists(file_path):
                            arcname = f"media/documents/{os.path.basename(file_path)}"
                            zip_file.write(file_path, arcname)
                            doc_data["fichier_pdf"] = arcname
                    except Exception:
                        pass
                chap_data["documents"].append(doc_data)

            # Devoirs
            for devoir in chap.devoirs.all():
                dev_data = {
                    "titre": devoir.titre,
                    "consigne": devoir.consigne,
                    "note_max": devoir.note_max,
                    "actif": devoir.actif,
                    "fichier_consigne": None
                }
                if devoir.fichier_consigne and devoir.fichier_consigne.name:
                    try:
                        file_path = devoir.fichier_consigne.path
                        if os.path.exists(file_path):
                            arcname = f"media/devoirs/{os.path.basename(file_path)}"
                            zip_file.write(file_path, arcname)
                            dev_data["fichier_consigne"] = arcname
                    except Exception:
                        pass
                chap_data["devoirs"].append(dev_data)

            manifest["cours"]["chapitres"].append(chap_data)

        # Écrire le manifest dans le ZIP
        zip_file.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    zip_buffer.seek(0)
    return zip_buffer, f"{cours.titre.replace(' ', '_')}.edutech"


def import_cours_edutech(zip_file_obj, createur=None):
    """
    Importe un cours depuis un fichier .edutech (ZIP).
    Re-crée l'arborescence et copie les fichiers dans le système de stockage.
    """
    try:
        with zipfile.ZipFile(zip_file_obj, 'r') as zip_ref:
            # Vérifier la présence du manifest
            if "manifest.json" not in zip_ref.namelist():
                return False, "Fichier manifest.json introuvable dans l'archive."
                
            manifest_data = zip_ref.read("manifest.json")
            manifest = json.loads(manifest_data)
            
            if manifest.get("type") != "edutech_cours":
                return False, "Format de fichier non reconnu."
                
            cours_data = manifest.get("cours", {})
            if not cours_data:
                return False, "Données du cours vides."

            with transaction.atomic():
                # Trouver ou créer le niveau (Fallback sur un niveau par défaut si non trouvé)
                niveau_code = cours_data.get("niveau_code")
                niveau = None
                if niveau_code:
                    niveau = Niveau.objects.filter(code=niveau_code).first()
                if not niveau:
                    niveau = Niveau.objects.first() # Sécurité

                # 1. Créer le cours
                cours = Cours.objects.create(
                    titre=cours_data.get("titre", "Cours importé"),
                    description=cours_data.get("description", ""),
                    niveau=niveau,
                    resume=cours_data.get("resume", ""),
                    actif=cours_data.get("actif", True),
                    createur=createur
                )

                # Extraire la cover si existante
                cover_path = cours_data.get("image_couverture")
                if cover_path and cover_path in zip_ref.namelist():
                    file_content = zip_ref.read(cover_path)
                    file_name = os.path.basename(cover_path)
                    cours.image_couverture.save(file_name, ContentFile(file_content), save=True)

                # 2. Créer les chapitres
                for chap_data in cours_data.get("chapitres", []):
                    chapitre = Chapitre.objects.create(
                        cours=cours,
                        titre=chap_data.get("titre", "Chapitre"),
                        description=chap_data.get("description", ""),
                        ordre=chap_data.get("ordre", 1),
                        url_video=chap_data.get("url_video", ""),
                        actif=chap_data.get("actif", True)
                    )

                    vid_path = chap_data.get("fichier_video")
                    if vid_path and vid_path in zip_ref.namelist():
                        file_content = zip_ref.read(vid_path)
                        file_name = os.path.basename(vid_path)
                        chapitre.fichier_video.save(file_name, ContentFile(file_content), save=True)

                    # Créer les documents
                    for doc_data in chap_data.get("documents", []):
                        doc = Document.objects.create(
                            chapitre=chapitre,
                            titre=doc_data.get("titre", "Document"),
                            type_document=doc_data.get("type_document", "RESSOURCE"),
                            description=doc_data.get("description", ""),
                            ordre=doc_data.get("ordre", 1),
                            actif=doc_data.get("actif", True)
                        )
                        pdf_path = doc_data.get("fichier_pdf")
                        if pdf_path and pdf_path in zip_ref.namelist():
                            file_content = zip_ref.read(pdf_path)
                            file_name = os.path.basename(pdf_path)
                            doc.fichier_pdf.save(file_name, ContentFile(file_content), save=True)

                    # Créer les devoirs
                    for dev_data in chap_data.get("devoirs", []):
                        devoir = Devoir.objects.create(
                            chapitre=chapitre,
                            titre=dev_data.get("titre", "Devoir"),
                            consigne=dev_data.get("consigne", ""),
                            note_max=dev_data.get("note_max", 20),
                            actif=dev_data.get("actif", True),
                            createur=createur
                        )
                        cons_path = dev_data.get("fichier_consigne")
                        if cons_path and cons_path in zip_ref.namelist():
                            file_content = zip_ref.read(cons_path)
                            file_name = os.path.basename(cons_path)
                            devoir.fichier_consigne.save(file_name, ContentFile(file_content), save=True)

            return True, cours.id

    except zipfile.BadZipFile:
        return False, "Le fichier n'est pas une archive ZIP valide."
    except Exception as e:
        return False, f"Erreur lors de l'importation: {str(e)}"
