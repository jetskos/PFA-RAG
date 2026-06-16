# Tuteur IA - Système d'Enseignement Pédagogique Multi-Agents

## Vue d'ensemble

Le module `tuteur_ia` intègre un système d'enseignement multi-agents basé sur LangGraph et LangChain dans la plateforme Django PFA-RAG. Le système utilise 4 agents pédagogiques spécialisés pour guider les étudiants dans l'apprentissage:

1. **Diagnostiqueur** : Évalue le niveau initial de l'étudiant
2. **Tuteur Socratique** : Pose des questions pour guider vers la compréhension
3. **Évaluateur** : Mesure le score de maîtrise (0.0-1.0)
4. **Mémoire** : Maintient le profil long-terme de l'étudiant

## Architecture

### Structure du dossier

```
tuteur_ia/
├── models.py                 # ProfilEtudiantIA, SessionTuteur
├── views.py                  # API Django (demarrer_session, repondre, statut)
├── urls.py                   # Routage des URLs
├── admin.py                  # Admin Django
├── apps.py                   # Configuration de l'app
├── agents/
│   ├── diagnostiqueur.py    # Agent diagnostique
│   ├── tuteur.py            # Tuteur Socratique (RAG)
│   ├── evaluateur.py        # Évaluation de maîtrise
│   └── memoire.py           # Mise à jour du profil
├── graph/
│   ├── state.py             # Définition du state LangGraph
│   └── workflow.py          # Orchestration du workflow
├── prompts/
│   ├── diagnostiqueur.py    # Prompts du diagnostiqueur
│   ├── tuteur.py            # Prompts du tuteur
│   ├── evaluateur.py        # Prompts d'évaluation
│   └── memoire.py           # Prompts de mémoire
├── tools/
│   └── rag_tool.py          # Recherche RAG sur Document.contenu_extrait
├── templates/tuteur_ia/
│   ├── session.html         # Interface de session
│   └── partials/
│       └── chat_message.html # Messages du chat
└── migrations/
    └── 0001_initial.py      # Migrations initiales
```

### Workflow LangGraph

```
START
  ↓
[diagnose] → Diagnostique le niveau initial
  ↓
[tutor] → Pose une question (enrichie par RAG)
  ↓
[INTERRUPT] → Attend la réponse de l'étudiant
  ↓
graph.update_state() + graph.stream() → Continue
  ↓
[evaluate] → Évalue la réponse (mastery_score)
  ↓
if mastery_score >= 0.75 ou iteration >= 5:
  → [memory] → Mise à jour du profil
  ↓
if next_action == "end":
  → END (session terminée)
else:
  → [tutor] (continuer)
```

### RAG (Retrieval-Augmented Generation)

Le RAG fonctionne sur `Document.contenu_extrait` (Django ORM), **pas sur des fichiers PDF locaux**:

```python
# rag_tool.py
def rag_search(query: str, chapitre_id: str, cours_id: str) -> str:
    # Recherche par mots-clés dans Document.contenu_extrait
    # Retourne les 2 meilleurs extraits pertinents
```

Le RAG est appelé par l'agent tuteur pour enrichir les questions avec du contexte pertinent du contenu du cours.

## Utilisation

### 1. Configuration initiale

#### Installation des dépendances
```bash
pip install -r requirements.txt
```

Fichier `requirements.txt`:
```
langgraph>=0.2.50
langchain>=0.3.0
langchain-core>=0.3.0
langchain-groq>=0.1.0
langchain-openai>=0.2.0
```

#### Configuration du LLM

Ajouter dans `.env`:
```
# Groq (recommandé pour les tests)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Ou OpenAI
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### Migrations Django
```bash
python manage.py makemigrations tuteur_ia
python manage.py migrate tuteur_ia
```

### 2. Vérifier l'installation
```bash
python manage.py test_tuteur_setup
```

### 3. Démarrer une session de tutorat

#### Via l'interface web
1. Créer un utilisateur avec `role='ELEVE'`
2. Se connecter à la plateforme
3. Naviguer vers un chapitre du cours
4. Cliquer sur "🤖 Demander à l'IA tuteur"

#### Via l'API
```bash
# Démarrer une session
POST /tuteur/session/<chapitre_id>/
Content-Type: application/json

# Répondre à une question
POST /tuteur/session/<session_id>/repondre/
Content-Type: application/json
{"message": "Réponse de l'étudiant"}

# Obtenir le statut
GET /tuteur/session/<session_id>/statut/
```

## API REST

### Endpoints

#### 1. Démarrer une session
```
GET /tuteur/session/<chapitre_id>/
```
**Réponse HTML** : Page de session du tuteur

```
POST /tuteur/session/<chapitre_id>/
```
**Réponse JSON**:
```json
{
  "session_id": "uuid",
  "message": "Première question du tuteur"
}
```

#### 2. Envoyer une réponse
```
POST /tuteur/session/<session_id>/repondre/
Content-Type: application/json
```
**Body**:
```json
{
  "message": "Réponse de l'étudiant"
}
```
**Réponse JSON**:
```json
{
  "message": "Question suivante du tuteur",
  "mastery_score": 0.65,
  "session_status": "EN_COURS"
}
```

#### 3. Obtenir le statut
```
GET /tuteur/session/<session_id>/statut/
```
**Réponse JSON**:
```json
{
  "session_id": "uuid",
  "statut": "EN_COURS",
  "mastery_score_final": null,
  "date_creation": "2026-05-22T10:30:00Z",
  "date_modification": "2026-05-22T10:32:00Z"
}
```

## Models Django

### ProfilEtudiantIA
Profil long-terme persisté pour chaque étudiant:
- `concepts_maitrises` : Concepts maîtrisés (≥0.8)
- `concepts_fragiles` : Concepts partiellement compris
- `erreurs_communes` : Erreurs récurrentes
- `style_prefere` : Préférence d'apprentissage (textuel, visuel, etc.)

### SessionTuteur
Persistance d'une session LangGraph:
- `etudiant` : FK vers Utilisateur
- `chapitre` : FK vers Chapitre
- `thread_id` : Identifiant unique du thread LangGraph
- `statut` : EN_COURS, TERMINEE, ABANDONNEE
- `mastery_score_final` : Score de maîtrise final (0.0-1.0)

## Méthode Pédagogique

### Socratique (Tuteur)
- Pose UNE question à la fois
- Jamais donner la réponse directe
- Encourager l'exploration autonome
- Adapter au niveau de l'étudiant

### Évaluation
Score de maîtrise (0.0-1.0):
- 0.0-0.3 : Compréhension très faible
- 0.3-0.6 : Compréhension partielle
- 0.6-0.8 : Bonne compréhension
- 0.8-1.0 : Maîtrise avancée/complète

**Progression** :
- ≥0.75 pendant 1 itération → Session terminée
- <0.75 mais ≤5 itérations → Continuer le tutorat
- ≥5 itérations → Terminer quelle que soit la maîtrise

## Limitations connues

1. **LLM requis** : Groq ou OpenAI API key obligatoire
2. **RAG basique** : Recherche par mots-clés, pas d'embeddings vectoriels
3. **MemorySaver** : Persistance en mémoire, pas sur disque (par session)
4. **Profil long-terme** : Persisté en Django, pas dans LangGraph

## Troubleshooting

### "Aucun LLM configuré"
**Solution** : Ajouter `GROQ_API_KEY` ou `OPENAI_API_KEY` dans `.env`

### "Chapitre non trouvé"
**Solution** : Créer un cours et un chapitre avant de démarrer

### "Erreur lors du démarrage"
**Solution** : 
1. Vérifier les logs Django
2. Lancer `test_tuteur_setup` pour diagnostiquer
3. Vérifier les migrations : `python manage.py migrate`

### Réponses du tuteur non cohérentes
**Solution** : 
1. Vérifier que `Document.contenu_extrait` est rempli
2. Améliorer les prompts dans `prompts/*.py`
3. Essayer un autre modèle LLM

## Développement et extension

### Ajouter un nouveau type de question
Modifier les prompts dans `tuteur_ia/prompts/tuteur.py`

### Améliorer le RAG
Remplacer `rag_search()` dans `tools/rag_tool.py` par:
- Embeddings vectoriels (Chroma, Pinecone)
- Recherche sémantique
- BM25 ou Elasticsearch

### Personnaliser l'évaluation
Modifier les critères d'évaluation dans `agents/evaluateur.py`

### Intégrer d'autres LLMs
Modifier `_get_llm()` dans chaque agent pour supporter:
- Gemini
- Claude (Anthropic)
- LLaMA (local)

## Notes techniques

- **Imports tardifs** : Les models Django sont importés dans les fonctions des agents pour éviter les erreurs d'initialisation
- **Thread ID** : Utilisé pour persister et reprendre les sessions LangGraph
- **Interrupt** : Le graph s'interrompt après chaque question du tuteur pour attendre une réponse
- **Stream mode "values"** : Retourne l'état complet après chaque nœud

## Références

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Documentation](https://python.langchain.com/)
- [Django Documentation](https://docs.djangoproject.com/)
