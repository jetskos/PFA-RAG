"""
Crée un cours de démonstration entièrement en anglais (contenu + PDF), portable
(aucun chemin machine en dur). Utilisé pour valider le point « Un cours en anglais ».

    python manage.py seed_english_course
"""
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from accounts.models import Niveau, Utilisateur
from apprentissage.models import Cours, Chapitre, Document


COURSE = {
    "titre": "Introduction to the Internet of Things (IoT)",
    "description": (
        "A hands-on introduction to the Internet of Things. Learn how everyday objects sense "
        "the world, exchange data over wireless networks, and use artificial intelligence to "
        "automate decisions."
    ),
    "resume": "Sensors, connectivity, data and AI — the building blocks of connected devices.",
    "chapitres": [
        {
            "titre": "Chapter 1 — What is the Internet of Things?",
            "description": "Definition, everyday examples, and the three layers of an IoT system.",
            "pdf_title": "Chapter 1 — Course notes",
            "pdf_body": [
                "What is the Internet of Things?",
                "The Internet of Things (IoT) is a network of physical objects that contain "
                "sensors, software and connectivity, allowing them to collect data and exchange "
                "it with other devices and systems over the internet.",
                "Everyday examples include smart thermostats, fitness trackers, connected door "
                "locks, agricultural soil sensors and industrial machine monitors.",
                "An IoT system has three layers: the perception layer (sensors and actuators), "
                "the network layer (the protocols that move the data), and the application "
                "layer (dashboards, alerts and automation logic).",
                "A sensor measures a physical quantity such as temperature, motion or light. "
                "An actuator changes the physical world, for example by switching a relay or "
                "opening a valve.",
            ],
        },
        {
            "titre": "Chapter 2 — How connected objects communicate",
            "description": "Wireless protocols: Wi-Fi, Bluetooth Low Energy, Zigbee and LPWAN (LoRaWAN, NB-IoT).",
            "pdf_title": "Chapter 2 — Course notes",
            "pdf_body": [
                "How connected objects communicate",
                "Connected objects use different wireless protocols depending on range, power "
                "budget and data rate.",
                "Wi-Fi offers a high data rate but consumes a lot of power, so it suits "
                "mains-powered devices such as cameras.",
                "Bluetooth Low Energy (BLE) is designed for short range and very low power, "
                "which is ideal for wearables and beacons.",
                "Zigbee builds a mesh network where each device relays messages for its "
                "neighbours, extending coverage inside a building.",
                "Low-Power Wide-Area Networks (LPWAN) such as LoRaWAN and NB-IoT trade a very "
                "low data rate for a range of several kilometres and a battery life measured "
                "in years. They are used for city-scale sensing like parking or water meters.",
            ],
        },
        {
            "titre": "Chapter 3 — From data to decisions with AI",
            "description": "Edge vs cloud processing, and how machine learning turns raw sensor data into action.",
            "pdf_title": "Chapter 3 — Course notes",
            "pdf_body": [
                "From data to decisions with AI",
                "Raw sensor data has little value on its own. It becomes useful when it is "
                "cleaned, aggregated and analysed.",
                "Edge processing runs the analysis directly on or near the device. It reduces "
                "latency and bandwidth, and keeps data local, which helps privacy.",
                "Cloud processing sends the data to a remote server that has more computing "
                "power, which is useful for training machine-learning models on large "
                "historical datasets.",
                "A typical pipeline is: collect data, detect anomalies with a model, then "
                "trigger an automated action such as sending an alert or adjusting a machine.",
                "Predictive maintenance is a common IoT-plus-AI application: vibration and "
                "temperature patterns are used to predict a failure before it happens.",
            ],
        },
    ],
}


def _make_pdf(title: str, paragraphs: list[str]) -> bytes:
    """Génère un petit PDF texte en anglais (reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 14)]
    for p in paragraphs:
        story.append(Paragraph(p, styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Crée un cours de démonstration entièrement en anglais (contenu + PDF)."

    def handle(self, *args, **options):
        createur = Utilisateur.objects.filter(role__in=["ADMIN", "FORMATEUR"]).first()
        if not createur:
            self.stdout.write(self.style.ERROR("Aucun utilisateur ADMIN/FORMATEUR — lancez d'abord seed_users ou seed_demo."))
            return

        # On rattache le cours au niveau d'un élève existant (démo seed_demo) pour qu'il
        # soit visible sans créer de classe ; à défaut, un niveau « English track ».
        eleve = Utilisateur.objects.filter(role="ELEVE", classe__isnull=False).select_related("classe__niveau").first()
        if eleve and getattr(eleve.classe, "niveau", None):
            niveau = eleve.classe.niveau
        else:
            niveau, _n = Niveau.objects.get_or_create(
                nom="English track", defaults={"code": "EN", "ordre": 9}
            )

        cours, created = Cours.objects.get_or_create(
            titre=COURSE["titre"],
            defaults={
                "description": COURSE["description"],
                "resume": COURSE["resume"],
                "niveau": niveau,
                "createur": createur,
                "actif": True,
            },
        )
        if not created:
            self.stdout.write(self.style.WARNING("Cours déjà présent — chapitres régénérés."))
            cours.chapitres.all().delete()
            cours.description = COURSE["description"]
            cours.resume = COURSE["resume"]
            cours.actif = True
            cours.save()

        try:
            from apprentissage.tasks import indexer_document_task
        except Exception:
            indexer_document_task = None

        for i, ch in enumerate(COURSE["chapitres"], start=1):
            chapitre = Chapitre.objects.create(
                cours=cours,
                titre=ch["titre"],
                description=ch["description"],
                ordre=i,
                actif=True,
            )
            pdf_bytes = _make_pdf(ch["pdf_title"], ch["pdf_body"])
            doc = Document.objects.create(
                chapitre=chapitre,
                titre=ch["pdf_title"],
                type_document="COURS",
                description="Course notes (English).",
                fichier_pdf=ContentFile(pdf_bytes, name=f"en_ch{i}_notes.pdf"),
            )
            # Indexation RAG (best effort — nécessite ChromaDB)
            if indexer_document_task is not None:
                try:
                    indexer_document_task(str(doc.id), doc.fichier_pdf.path)
                except Exception as exc:  # pragma: no cover
                    self.stdout.write(self.style.WARNING(f"  indexation IA ignorée : {exc}"))
            self.stdout.write(f"  + {ch['titre']}")

        self.stdout.write(self.style.SUCCESS(
            f"\nCours anglais créé : « {cours.titre} » — {cours.chapitres.count()} chapitres, PDF inclus."
        ))
