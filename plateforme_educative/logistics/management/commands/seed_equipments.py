from logistics.models import Equipment
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Génère la base de données démo pour les équipements IoT'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- Lancement du Seeder : Équipements IoT ---")

        equipments_data = [
            {"nom": "Arduino Uno Rev3", "reference": "ARD-UNO-001", "stock": 25, "seuil": 5, "note": "Microcontrôleur classique idéal pour débutants."},
            {"nom": "Arduino Mega 2560", "reference": "ARD-MEGA-001", "stock": 10, "seuil": 3, "note": "Pour projets nécessitant beaucoup de broches I/O."},
            {"nom": "ESP32 Wi-Fi & Bluetooth", "reference": "ESP32-001", "stock": 30, "seuil": 10, "note": "Module IoT complet avec connectivité sans fil intégrée."},
            {"nom": "NodeMCU ESP8266", "reference": "ESP8266-001", "stock": 20, "seuil": 5, "note": "Très populaire pour la domotique de base."},
            
            # Capteurs
            {"nom": "Capteur de température DHT11", "reference": "SENS-DHT11-01", "stock": 40, "seuil": 10, "note": "Mesure basique température et humidité."},
            {"nom": "Capteur Ultrason HC-SR04", "reference": "SENS-HCSR04-01", "stock": 35, "seuil": 10, "note": "Pour la mesure de distance et les robots évitant les obstacles."},
            {"nom": "Détecteur de mouvement PIR", "reference": "SENS-PIR-01", "stock": 20, "seuil": 5, "note": "Utilisé pour la détection de présence (Maison intelligente)."},
            
            # Actionneurs
            {"nom": "Servomoteur SG90", "reference": "ACT-SERVO-01", "stock": 50, "seuil": 15, "note": "Petit moteur pour les articulations de robots."},
            {"nom": "Moteur CC avec roue", "reference": "ACT-DC-WHEEL-01", "stock": 40, "seuil": 10, "note": "Pour la création de voitures connectées."},
            {"nom": "Relais 5V (1 Canal)", "reference": "ACT-RELAY-01", "stock": 30, "seuil": 10, "note": "Pour contrôler des appareils haute tension en domotique."},
            
            # Composants de base
            {"nom": "Potentiomètre 10K", "reference": "COMP-POT-10K", "stock": 100, "seuil": 20, "note": "Pour varier une valeur analogique."},
            {"nom": "LED (Lot de 50 - Rouge/Vert/Bleu)", "reference": "COMP-LED-MIX", "stock": 15, "seuil": 5, "note": "Composant de base de retour visuel."},
            {"nom": "Breadboard (Plaque d'essai)", "reference": "COMP-BREAD-01", "stock": 40, "seuil": 10, "note": "Plaque pour prototyper sans soudure."},
            
            # Câbles
            {"nom": "Câbles Jumper Mâle-Mâle (Lot 40)", "reference": "CABLE-MM-40", "stock": 60, "seuil": 15, "note": "Câbles de prototypage basiques."},
            {"nom": "Câbles Jumper Mâle-Femelle (Lot 40)", "reference": "CABLE-MF-40", "stock": 60, "seuil": 15, "note": "Utile pour brancher les capteurs ESP32."},
            {"nom": "Câble USB A vers B (Pour Arduino)", "reference": "CABLE-USB-AB", "stock": 25, "seuil": 5, "note": "Alimentation et programmation de l'Arduino Uno."},
            {"nom": "Câble Micro-USB", "reference": "CABLE-USB-MICRO", "stock": 30, "seuil": 5, "note": "Pour l'alimentation des ESP32."},
        ]

        # On supprime d'abord les anciens pour faire place nette
        Equipment.objects.all().delete()

        for data in equipments_data:
            Equipment.objects.create(
                nom=data["nom"],
                reference=data["reference"],
                stock_total=data["stock"],
                stock_disponible=data["stock"],  # Au début, tout le stock est disponible
                seuil_alerte=data["seuil"],
                note=data["note"],
                est_actif=True
            )
            self.stdout.write(f"  - Equipement ajoute : {data['nom']} ({data['reference']})")

        self.stdout.write(self.style.SUCCESS(f"\nBase de donnees logistique initialisee avec {len(equipments_data)} equipements IoT !"))
