<div align="center">
  
# 🎓 Plateforme Éducative Intelligente (IoT & RAG)
**Un LMS de nouvelle génération propulsé par l'Intelligence Artificielle (RAG) et HTMX.**

[![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white)]()
[![HTMX](https://img.shields.io/badge/htmx-336699?style=for-the-badge&logo=htmx&logoColor=white)]()
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)]()
[![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6F00?style=for-the-badge)]()
[![MySQL](https://img.shields.io/badge/MySQL-005C84?style=for-the-badge&logo=mysql&logoColor=white)]()

</div>

---

## 📖 À propos du projet (PFA-RAG)

Ce projet de fin d'année (PFA) est une plateforme éducative moderne spécialisée dans l'Internet des Objets (IoT) et l'Intelligence Artificielle. Conçue pour offrir une expérience utilisateur (UX) ultra-premium et fluide, elle intègre un système d'IA contextuelle utilisant la technologie **RAG (Retrieval-Augmented Generation)**. 

Plutôt que d'utiliser une IA générique, la plateforme intègre un **Tuteur IA** capable de répondre aux questions des étudiants en se basant *exclusivement* sur le contenu des cours (via ChromaDB et LangChain), tout en générant automatiquement des évaluations (QCM) pour les professeurs.

## ✨ Fonctionnalités Principales

### 👨‍🎓 Espace Élève
- **Apprentissage immersif :** Interface de lecture des cours moderne et sans distraction.
- **Tuteur IA Contextuel (RAG) :** Un chatbot intégré à chaque chapitre, capable d'expliquer les concepts techniques en lisant les données réelles du cours.
- **Évaluation :** Passage de QCM interactifs et suivi visuel de la progression.

### 👨‍🏫 Espace Formateur
- **Création de contenu :** Éditeur de cours et de chapitres.
- **Génération IA de QCM :** Génération automatique de questionnaires basés sur le texte du chapitre via l'API LLM (Groq/Ollama).
- **Logistique :** Demandes de matériel IoT (Arduino, Raspberry Pi) intégrées au tableau de bord.

### 🛡️ Tableau de Bord Administrateur (Full HTMX)
- **Gestion Hiérarchique CRUD :** Gestion complète des *Niveaux*, *Classes*, et *Étudiants* sur des pages dédiées.
- **Fluidité absolue :** L'interface d'administration utilise **HTMX** pour des changements d'état asynchrones ultra-rapides, sans rechargement de page (Single Page Application feel).
- **Validation des comptes :** Système d'approbation et d'assignation des étudiants aux classes.

---

## 🛠️ Stack Technique & Architecture

L'architecture vise la performance, la maintenabilité, et l'intégration profonde des LLMs.

**Frontend :**
- HTML5 sémantique avec un design **Glassmorphism Premium** (Vanilla CSS structuré).
- **HTMX :** Pour des interactions dynamiques (modales, onglets, requêtes asynchrones) sans la lourdeur de React ou Vue.js.

**Backend :**
- **Django (Python) :** Framework principal gérant l'authentification personnalisée, le routage, et la logique métier.
- **MySQL :** Base de données relationnelle robuste pour stocker les profils, les progressions et les cours.

**Intelligence Artificielle (RAG Pipeline) :**
- **LangChain :** Orchestration des requêtes LLM.
- **ChromaDB :** Base de données vectorielle locale pour stocker les "embeddings" des chapitres de cours.
- **Groq API / Ollama :** Moteur LLM utilisé pour la génération de texte rapide et l'inférence.

---

## 🚀 Installation & Déploiement Local

### Prérequis
- Python 3.10+
- MySQL Server (en cours d'exécution sur le port 3307 ou ajustez `settings.py`)
- Un compte Groq (pour `GROQ_API_KEY`) ou Ollama installé localement.

### Étapes de configuration

1. **Cloner le repository :**
   ```bash
   git clone https://github.com/jetskos/PFA-RAG.git
   cd PFA-RAG/plateforme_educative
   ```

2. **Créer l'environnement virtuel et installer les dépendances :**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configuration de la Base de données & Variables d'environnement :**
   Créez un fichier `.env` à la racine de `plateforme_educative/` avec vos identifiants :
   ```env
   SECRET_KEY=votre_cle_django_secrete
   DB_NAME=rag_platform1
   DB_USER=root
   DB_PASSWORD=votre_mot_de_passe
   DB_HOST=127.0.0.1
   DB_PORT=3307

   # Configuration IA
   USE_LOCAL_LLM=False
   GROQ_API_KEY=gsk_votre_cle_groq
   ```

4. **Migrations et Superuser :**
   ```bash
   python manage.py makemigrations accounts apprentissage logistics tuteur_ia
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. **Lancer le serveur de développement :**
   ```bash
   python manage.py runserver
   ```
   *Accédez à la plateforme sur `http://127.0.0.1:8000/`*

---

## 📂 Structure du Code

- `core/` : Vues principales, tableau de bord, configurations globales et URLs.
- `accounts/` : Modèle utilisateur personnalisé, gestion des profils, authentification.
- `apprentissage/` : Modèles des cours, chapitres, progression des élèves.
- `tuteur_ia/` : Logique de l'Intelligence Artificielle (RAG, ChromaDB, Langchain, Génération QCM).
- `logistics/` : Gestion de l'inventaire matériel et demandes des professeurs.
- `static/core/css/` : Fichiers CSS Premium (app.css, ia_premium.css).

---

## 🤝 Contribution & Équipe

Ce projet a été développé dans le cadre d'un Projet de Fin d'Année (PFA). 
- **Auteur :** Youssef Rahahli et Malek Mohamed Aymen
- **Supervision :** emsi

*Si vous souhaitez contribuer ou suggérer des améliorations, n'hésitez pas à ouvrir une Issue ou soumettre une Pull Request !*
