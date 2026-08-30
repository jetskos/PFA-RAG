import io
from datetime import timedelta

from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password

from accounts.models import Utilisateur, Niveau, Classe
from apprentissage.models import Cours, Chapitre, Devoir, Document


def _make_pdf(title: str, paragraphs: list) -> bytes:
    """Petit PDF texte (reportlab) — sert de support de cours indexable par le RAG."""
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


CHAPITRES_DATA = [
    {
        "titre": "Dans les secrets des objets connectés ?! Mon monde, mes ordres !",
        "desc": "Je présente mon invention ! L'Aventure avec Nova. Découvre comment les objets autour de toi communiquent.",
        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "tp_titre": "Dessine ton premier objet connecté",
        "tp_desc": "Imagine un objet de ton quotidien. Comment pourrait-il être connecté pour t'aider ? Dessine-le et explique ses fonctions.",
        "doc_titre": "Objets connectés — notes de cours",
        "doc_type": "COURS",
        "pdf_body": [
            "Un objet connecté est un objet du quotidien (montre, ampoule, thermostat, jouet) auquel on a ajouté trois choses : un capteur qui mesure quelque chose, un petit ordinateur qui décide, et une connexion sans fil qui échange des informations.",
            "L'Internet des objets, ou IoT (Internet of Things), désigne l'ensemble de ces objets qui communiquent entre eux et avec nous à travers un réseau, sans que l'on ait besoin de tout commander à la main.",
            "Un objet connecté fonctionne toujours en trois temps : il perçoit (le capteur lit la température, la lumière, un mouvement), il transmet l'information par Wi-Fi ou Bluetooth, puis il agit (allumer, envoyer une alerte, afficher une valeur).",
            "Exemples : une montre connectée compte tes pas et mesure ton rythme cardiaque ; une ampoule connectée s'allume quand ton téléphone entre dans la maison ; un capteur de porte prévient tes parents quand la porte s'ouvre.",
            "Le capteur est l'organe des sens de l'objet. Sans capteur, l'objet est aveugle : il ne peut rien mesurer et donc rien décider.",
        ],
    },
    {
        "titre": "La maison intelligente : quand ta maison t'aide toute seule !",
        "desc": "Ma maison, mon super-héros. Apprends comment une maison peut allumer la lumière ou faire le café toute seule.",
        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "tp_titre": "Mission : Maison Intelligente",
        "tp_desc": "Liste 3 choses que ta maison intelligente ferait pour toi le matin avant d'aller à l'école.",
        "doc_titre": "La maison intelligente — notes de cours",
        "doc_type": "COURS",
        "pdf_body": [
            "Une maison intelligente (ou maison connectée) est une maison équipée d'objets connectés qui travaillent ensemble pour rendre la vie plus simple, plus sûre et moins gourmande en énergie.",
            "Le cerveau de la maison intelligente s'appelle la box domotique ou l'assistant central. C'est lui qui reçoit les informations de tous les capteurs et qui donne les ordres aux appareils.",
            "On programme la maison avec des scénarios : « quand il fait nuit ET que quelqu'un rentre, alors allume l'entrée ». Un scénario est une règle du type SI... ALORS.",
            "Les usages les plus courants sont l'éclairage automatique, le chauffage qui baisse quand personne n'est là, les volets qui se ferment le soir, et les alertes en cas de fuite d'eau ou de fumée.",
            "La maison intelligente permet d'économiser de l'énergie : elle n'allume et ne chauffe que ce qui est utile, au bon moment.",
        ],
    },
    {
        "titre": "Les machines peuvent-elles APPRENDRE ? L'IA expliquée aux enfants",
        "desc": "Ils apprennent ?! Découvre ce qu'est l'Intelligence Artificielle et comment un robot apprend à reconnaître un chat.",
        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "tp_titre": "Apprends à ton robot",
        "tp_desc": "Choisis un animal. Quelles sont les 3 règles (oreilles, poils, etc.) que tu donnerais à ton robot pour qu'il le reconnaisse ?",
        "doc_titre": "L'intelligence artificielle — notes de cours",
        "doc_type": "COURS",
        "pdf_body": [
            "L'intelligence artificielle (IA) désigne des programmes informatiques capables de faire des tâches qui demandent normalement de l'intelligence humaine : reconnaître une image, comprendre une phrase, jouer à un jeu.",
            "Une IA n'apprend pas comme un élève avec un professeur. On lui montre des milliers d'exemples (des milliers de photos de chats et de photos qui ne sont pas des chats) et elle repère toute seule les points communs.",
            "Cette phase s'appelle l'entraînement. Après l'entraînement, on peut lui montrer une photo qu'elle n'a jamais vue et elle devine : « c'est un chat » avec un pourcentage de confiance.",
            "L'IA se trompe si les exemples d'entraînement étaient mauvais ou trop peu nombreux. La qualité des données est plus importante que la quantité de code.",
            "Exemples d'IA dans la vie courante : la reconnaissance vocale, les suggestions de vidéos, les filtres photo, la traduction automatique.",
        ],
    },
    {
        "titre": "Où va l'info ? WiFi, Bluetooth, Cloud",
        "desc": "Le chemin magique d'internet. Comment les informations voyagent dans les airs !",
        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "tp_titre": "Le parcours du message",
        "tp_desc": "Trace sur une feuille le chemin qu'emprunte un message de ton téléphone jusqu'à celui de ton ami.",
        "doc_titre": "Les réseaux — notes de cours",
        "doc_type": "COURS",
        "pdf_body": [
            "Un réseau, c'est un ensemble d'appareils reliés entre eux pour échanger des informations. Internet est le plus grand réseau du monde : il relie des milliards d'ordinateurs.",
            "Le Wi-Fi est une connexion sans fil de courte portée (une maison, une classe) qui relie tes appareils à la box, elle-même reliée à Internet par un câble.",
            "Le Bluetooth est une connexion sans fil de très courte portée (quelques mètres) pour relier deux appareils proches : un casque au téléphone, une manette à la console.",
            "Le Cloud (« le nuage ») désigne des ordinateurs très puissants, situés dans de grands bâtiments appelés centres de données, où l'on stocke des fichiers et où tournent des programmes accessibles depuis n'importe où.",
            "Quand tu envoies un message, il est découpé en petits morceaux appelés paquets. Chaque paquet voyage par le chemin le plus rapide, puis les paquets sont remis dans l'ordre à l'arrivée.",
        ],
    },
    {
        "titre": "Ils parlent pour de vrai ?! Assistants vocaux",
        "desc": "Coucou, tu bois quoi ?! Je t'ai fait un toast ! Découvre comment les machines comprennent la voix humaine.",
        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "tp_titre": "Crée ta commande vocale",
        "tp_desc": "Invente la commande vocale parfaite pour faire tes devoirs plus vite.",
        "doc_titre": "Les assistants vocaux — notes de cours",
        "doc_type": "COURS",
        "pdf_body": [
            "Un assistant vocal est un programme qui écoute ta voix, comprend ta demande et répond ou déclenche une action. On en trouve dans les téléphones, les enceintes connectées et les voitures.",
            "L'assistant fonctionne en quatre étapes : il capte le son avec un micro, il transforme le son en texte (reconnaissance vocale), il comprend l'intention de la phrase, puis il agit et répond avec une voix de synthèse.",
            "Le « mot de réveil » (par exemple « Ok Google » ou « Alexa ») sert à dire à l'assistant qu'on s'adresse à lui. Avant ce mot, il n'envoie rien sur Internet.",
            "La reconnaissance vocale utilise de l'intelligence artificielle entraînée sur des milliers d'heures d'enregistrements de voix différentes, avec des accents variés.",
            "Attention à la vie privée : l'assistant envoie parfois ta demande à des serveurs distants pour la comprendre. Il faut réfléchir à ce qu'on dit devant un objet connecté.",
        ],
    },
]


class Command(BaseCommand):
    help = 'Génère la base de données démo Génération Smart (Primaire), PDF de cours FR inclus et indexés.'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- Lancement du Seeder : Génération Smart ---")

        # 1. Niveau & Classe
        niveau, _ = Niveau.objects.get_or_create(nom="Débutant (Primaire)", defaults={'ordre': 1})
        classe, _ = Classe.objects.get_or_create(nom="Génération Smart", annee_scolaire="2025-2026", defaults={'niveau': niveau})
        self.stdout.write(self.style.SUCCESS("Niveau 'Débutant (Primaire)' et Classe créés."))

        # 2. Utilisateurs
        formateur, _ = Utilisateur.objects.get_or_create(email='prof@smart.com', defaults={
            'first_name': 'Prof', 'last_name': 'Smart', 'role': 'FORMATEUR', 'is_formateur': True,
            'statut_compte': 'ACTIVE', 'is_active': True, 'password': make_password('prof123')
        })

        for i in range(1, 4):
            Utilisateur.objects.get_or_create(email=f'enfant{i}@smart.com', defaults={
                'first_name': 'Enfant', 'last_name': str(i), 'role': 'ELEVE', 'classe': classe,
                'statut_compte': 'ACTIVE', 'is_active': True, 'password': make_password('enfant123')
            })
        self.stdout.write(self.style.SUCCESS("Professeur et Élèves créés."))

        # 3. Cours
        cours, _ = Cours.objects.get_or_create(
            titre="Génération Smart : La Technologie expliquée aux enfants",
            createur=formateur,
            defaults={
                'description': "Bienvenue sur Génération Smart ! Découvre les secrets des objets connectés, de l'IA et des maisons intelligentes en t'amusant.",
                'niveau': niveau,
                'resume': "La chaîne où la technologie devient un jeu d'enfant !",
                'actif': True
            }
        )

        try:
            from apprentissage.tasks import indexer_document_task
        except Exception:
            indexer_document_task = None

        # 4. Chapitres, Documents (PDF générés + indexés) et Devoirs
        Chapitre.objects.filter(cours=cours).delete()

        for idx, c_data in enumerate(CHAPITRES_DATA, 1):
            chapitre = Chapitre.objects.create(
                cours=cours,
                titre=c_data['titre'],
                description=c_data['desc'],
                ordre=idx,
                url_video=c_data['url']
            )

            Devoir.objects.create(
                chapitre=chapitre,
                titre=c_data['tp_titre'],
                consigne=c_data['tp_desc'],
                date_limite=timezone.now() + timedelta(days=7),
                note_max=20,
                createur=formateur,
                actif=True
            )

            pdf_bytes = _make_pdf(c_data['doc_titre'], c_data['pdf_body'])
            doc = Document.objects.create(
                chapitre=chapitre,
                titre=c_data['doc_titre'],
                type_document="COURS",
                ordre=1,
                description=f"Support de cours pour le chapitre : {c_data['titre']}",
                fichier_pdf=ContentFile(pdf_bytes, name=f"seed_fr_ch{idx}_notes.pdf"),
            )

            if indexer_document_task is not None:
                try:
                    indexer_document_task(str(doc.id), doc.fichier_pdf.path)
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(f"  indexation IA ignorée (ch{idx}) : {exc}"))

            self.stdout.write(f"  - Chapitre {idx} cree : {c_data['titre']}")

        self.stdout.write(self.style.SUCCESS("\nBase de donnees Generation Smart initialisee (PDF FR indexes) !"))
        self.stdout.write(self.style.WARNING("-> Compte Formateur : prof@smart.com (mdp: prof123)"))
        self.stdout.write(self.style.WARNING("-> Compte Eleve : enfant1@smart.com (mdp: enfant123)"))
