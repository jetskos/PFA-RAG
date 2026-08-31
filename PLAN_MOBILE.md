# PLAN_MOBILE.md — Refonte du design mobile

> Périmètre : responsive < 768 px. Le desktop (≥ 769 px) ne doit pas bouger.
> Méthode : parcours navigateur à 375 px (viewport 375×812), connecté
> successivement en visiteur / élève (`enfant1@smart.com`) / formateur
> (`prof@smart.com`) / admin (`admin@smart.com`).

## Journal d'exécution

| Phase | Commit | Contenu |
|-------|--------|---------|
| 0 — audit | `a1e78c3` | ce fichier |
| 1 — coquille | `7070c3c` | en-tête **1 rangée** (G1) ; FR/EN à plat (G3) |
| 2 — design system | `c221059` | tokens `--m-*` + gouttière unique 1 rem, fin du double padding (G7) ; cibles tactiles ≥ 44 px étendues (G8) ; filet typo h1/h2/h3 |
| 3.1 — auth | `670f602` | inscription/connexion : plus de double logo (G9), plus de vide mort (1er champ −130 px), pages « carte » |
| 3.2 — cours | *(RAS)* | catalogue (`::before` déco inoffensif), détail cours/chapitre déjà OK |
| 3.3 — tuteur IA | `34e961e` | **session : composeur qui passait sous la barre du bas → corrigé** ; barre du haut condensée ~410 → ~180 px |
| 3.4 — dashboards | `0d68c75` | cartes d'accès rapide élève « icône d'appli » (titres ne cassent plus) ; radar OK ; graphiques admin plafonnés 200 px |
| 3.5 — formulaires | *(RAS)* | cours/gérer/événement/calendrier/wizard : déjà propres après Phase 2 |
| 3.6 — logistique + gestion | `513ec63` | **gestion users : 47 px de scroll-x → corrigé** (`<select>` masqué TomSelect sorti de l'écran) ; puces de rôle qui passent à la ligne ; `.logi-subtab` ≥ 44 px |
| 4 — composants dynamiques | `<en cours>` | menu latéral / dropdowns notifs + profil / FAB tuteur / panneau tuteur : re-vérifiés OK ; **toasts remontés au-dessus de la barre du bas** ; **modales : z-index > nav (1100), ancrées en haut + `overflow-y:auto` + `max-height` → le bouton « Enregistrer » d'un formulaire long est de nouveau atteignable** |

---

## Constats initiaux (Phase 0)

---

## 1. Constats globaux (présents sur ~toutes les pages)

| ID | Constat | Preuve | Correctif proposé | Risque | Fait |
|----|---------|--------|-------------------|--------|------|
| **G1** | **En-tête sur 2 rangées.** ~~`.brand` est centré (marges auto)~~ **CAUSE RÉELLE : `base.css` `@media (max-width:640px) { .header-inner { flex-direction:column } }`** (bloc hérité). `.header-inner` fait `scrollHeight = 88 px` pour `clientHeight = 48 px`. | toutes les pages | ✅ **FAIT (commit Phase 1)** : bloc 640 px vidé dans base.css ; `responsive.css @≤768px` force `.header-inner { flex-direction:row; min-height:52px }` + `.header-actions { margin:0; flex:0 0 auto }`. Vérifié 375 px (visiteur + élève) : 1 rangée 55 px, `horizScroll:0`, bord droit à 359/375. Desktop 1280 px inchangé. | Faible | [x] |
| **G2** | **`.header-actions` déborde à droite.** Résolu par G1 (une seule rangée, `flex:0 0 auto`, `justify-content:flex-end`). Reste serré : élève = bell+thème+FR/EN+avatar → bord droit 359/375 (16 px de marge). | capture téléphone (inscription) | ✅ **FAIT (Phase 1)** — tient sur 360 px aussi. Marge à surveiller si un 5ᵉ élément apparaît. | Faible | [x] |
| **G3** | **Pastille FR / EN « flottante ».** `.lang-switch-track` = pilule blanche bordée `border-radius:20px` posée sur un en-tête clair → détachée. | toutes les pages | ✅ **FAIT (Phase 1)** : gardée dans l'en-tête mobile mais **à plat** — `.lang-switch-track` fond transparent + sans bordure, bouton actif = texte teal souligné (plus de pilule pleine). Desktop garde la pilule d'origine (règle scopée `@≤768px`). *(choix : gardée en header plutôt que déplacée dans le drawer → moins de risque, pas de modif DOM/JS ; à rediscuter si tu préfères la version drawer.)* | Faible | [x] |
| **G4** | **Navigation dupliquée en 3 exemplaires.** Header (liens nav + connexion / inscription) ⟂ barre du bas ⟂ menu latéral. | toutes les pages | ⚠️ **PARTIEL / choix assumé** : sur mobile les liens de nav du header sont déjà l'off-canvas `.main-nav` (invisibles dans la barre) ; l'en-tête ne montre que thème + cloche + FR/EN + avatar. La redondance *visuelle* (encombrement) est réglée par la Phase 1. Non fait : descendre FR/EN dans le tiroir + retirer les boutons connexion/inscription du header visiteur (nécessite modif DOM/JS ; FR/EN gardé à plat dans le header à la place). À rediscuter si tu veux la version « tout dans le tiroir ». | Moyen | [~] |
| **G5** | ~~Barre du bas admin = 5 items → libellés tronqués~~ **FAUX POSITIF** : vérifié à 375 px, les 5 libellés rendent en entier, non clippés. Le « Utilisateu » venait d'un `.slice(0,10)` du script d'audit. | — | RAS. | ✅ rien à faire |
| **G6** | `.main-nav` reste `display:flex` (fixed, hors écran) quand le menu est fermé. Apparaît dans les scans d'overflow (positions négatives) mais `transform: translateX(-101%)` le sort de l'écran → **aucun impact visuel ni fonctionnel**. | toutes les pages | ⏭️ **NON FAIT — priorité basse** (purement cosmétique côté outillage d'audit). `@media(max-width:768px){ .main-nav:not(.open){visibility:hidden} }` si un jour on veut nettoyer. | Faible | [ ] |
| **G7** | **Pas d'échelle d'espacement partagée + double padding.** `.site-main` = 12 px latéral **+** `.db-shell` 14 px = **26 px** de chaque côté. | comparaison inter-pages | ✅ **FAIT (Phase 2)** : tokens `--m-1..--m-6` + `--page-gutter: 1rem` dans `:root` ; `.site-main` = **1 rem latéral unique** ; `.site-main > [class*="-shell"] / .fmt-wrap / .main-wrap / .conteneur` → retrait latéral 0 (plus de double padding). Vérifié dashboards élève + formateur (gouttière 16 px, `scroll-x:0`). *Application fine des tokens aux marges de section = Phase 3.* | Moyen | [x] |
| **G8** | **Cibles tactiles < 44 px non couvertes.** `.btn-fmt` (37), `.btn-sm` (32), `.fmt-link` (27), `.admin-filter-btn`, sous-nav logistique, `input[type=checkbox]` (17). Dashboard formateur = **10 cas**. | formateur (10), logistique (5), gestion | ✅ **FAIT (Phase 2)** : règle globale `min-height:44px` étendue à `.btn-fmt/.btn-sm/.admin-filter-btn/a.btn-fmt/a.btn-sm` ; `.fmt-link/.profile-nav__tab/.logi-subnav a/.devoirs-tabs>a` → `min-height:44px; display:inline-flex` ; checkboxes/radios ≥ 20 px. **Dashboard formateur : 10 → 1 cible < 40 px** (reste `.brand`, logo, volontairement laissé). | Faible | [x] |
| **G9** | **Double branding sur les pages d'auth** : logo « EduTech » dans le header **+** logo « EduTech IoT & IA » dans la carte. | inscription, connexion | Sur mobile, masquer le bloc-logo interne de la carte auth (le header suffit), OU masquer le wordmark du header sur les routes `/auth/*`. | Faible. | [ ] |

---

## 2. Tableau par page

Légende risque : 🟢 faible · 🟡 moyen · 🔴 élevé (touche DOM/JS ou desktop).

| Page (route) | Rôle | Défauts constatés | Correctif proposé | Risque | Fait |
|---|---|---|---|---|---|
| **Accueil** `/fr/` | visiteur | G1–G4. Bouton connexion du header coupé. Hero déjà correct. | G1–G4. Rien de plus sur le hero. | 🟡 | [ ] |
| **Inscription** `/fr/auth/register/` | visiteur | G1–G4, G9. **Vide ~100 px** entre le sous-titre et le 1er champ. Labels surdimensionnés (gras ~17 px), chaque bloc de champ ~195 px. Lien « Se connecter » = cible 16 px. Page 1,7 écran pour 4 champs. | Supprimer l'espace mort (marge après `.auth-subtitle` / avant `.auth-form`). Labels 0.9 rem. `--m-*` entre les champs. Lien « Se connecter » en bouton ≥ 44 px. | 🟢 | [ ] |
| **Connexion** `/fr/auth/login/` | visiteur | G1–G4, G9. 1,1 écran sinon OK. | idem inscription (mise en page auth commune). | 🟢 | [ ] |
| **Compte en attente** `/fr/auth/pending/` | visiteur | À auditer (non rendu — nécessite un compte non activé). | Appliquer la mise en page auth commune. | 🟢 | [ ] |
| **Mot de passe oublié** `/fr/auth/password-reset/` | visiteur | À auditer. | idem auth commune. | 🟢 | [ ] |
| **Onboarding** `/fr/auth/onboarding/` | élève/formateur | À auditer (4 étapes). Noté « correct » en session précédente. | Vérifier boutons d'étape empilés ≥ 46 px, pas de débordement. | 🟡 | [ ] |
| **Catalogue** `/fr/apprentissage/` | tous | G1–G4. `.catalog-hero` a un `scrollWidth` interne de 415 px (rangée de puces / stats non contenue). Sinon 1,1 écran, propre. | Envelopper la rangée de puces du hero dans un conteneur `overflow-x:auto` **ou** la passer en `flex-wrap:wrap`. | 🟢 | [ ] |
| **Détail cours** `/fr/apprentissage/cours/<id>/` | élève | À re-vérifier (redirige souvent vers le 1er chapitre). | Vérifier hero + liste chapitres 1 colonne. | 🟡 | [ ] |
| **Détail chapitre** `/fr/apprentissage/cours/<id>/chapitre/<id>/` | élève | **OK** — corrigé au commit `2594af7` (fil d'Ariane réduit, titre `clamp()`, 3,1 écrans, 0 débordement). | RAS — juste vérifier après refonte de l'en-tête global. | 🟢 | [ ] |
| **Session socratique** `/fr/tuteur/session/<id>/` | élève | 🔴 **L'input du chat passe SOUS la barre du bas** : bas du composeur à y=831, barre du bas à y=747 → **~84 px cachés**, bouton « envoyer » coupé. **~470 px de « chrome »** (cartes Maîtrise / En cours / Seuil de validation + « Retour au cours » + en-tête « Tuteur IA ») avant la conversation. Grand vide sous le 1er message. Page auto-scrollée au chargement (en-tête hors vue). | Réserver `padding-bottom` = hauteur barre du bas + safe-area sur `.ia-chat-area` / le composeur, OU masquer la barre du bas sur cette route. Condenser les cartes du haut en **une seule barre compacte** (Maîtrise X % · Question n/N · seuil) collante. `.ia-chat-area` en `height: calc(100dvh - <chrome> )` avec le composeur **sticky bottom**. | 🔴 (mise en page structurelle, CSS + peut-être 1 classe HTML) | [ ] |
| **QCM** `/fr/tuteur/qcm/<id>/` | élève | En-tête réagencé au commit `2594af7` (OK). Corps (cartes questions, pastilles de progression, barre de nav bas) **non audité en profondeur**. | Vérifier cartes questions 1 colonne, options ≥ 46 px, barre d'actions empilée. | 🟡 | [ ] |
| **Résultats QCM** `/fr/tuteur/qcm/<id>/resultats/` (ou équiv.) | élève | À auditer. | Vérifier `.stats-row` en 2–3 colonnes compactes, pas de débordement. | 🟡 | [ ] |
| **Tableau de bord élève** `/fr/dashboard/student/` | élève | G1–G4. **`.radar-panel` déborde** (canvas Chart.js / `min-width` du panneau). **Cartes d'action rapide** en `flex-direction:row` : le texte casse sur 5 lignes (« Mes » / « cours » / « Parcourir » / « les » / « modules »), cartes ~245 px pour très peu de contenu. 2,9 écrans. | `.radar-panel`/`.panel` : `min-width:0`, canvas `max-width:100%`. Cartes rapides : soit `flex-direction:column` (icône en haut, titre, sous-titre) soit garder `row` avec icône 36 px + colonne texte `min-width:0` et titres qui ne cassent pas mot à mot. Réduire la hauteur des cartes. | 🟡 | [ ] |
| **Carnet de notes** `/fr/apprentissage/notes/` | élève | Règles ajoutées en session précédente — à re-vérifier (tableau/latéral). | Vérifier tableau dans conteneur scrollable, filtres empilés. | 🟡 | [ ] |
| **Mes devoirs** `/fr/apprentissage/devoirs/` | élève | Idem — à re-vérifier (onglets `.devoirs-tabs`). | Onglets en `overflow-x:auto` ou wrap ; cartes 1 colonne. | 🟡 | [ ] |
| **Calendrier** `/fr/apprentissage/calendrier/` | élève | Bascule FullCalendar en `listMonth` sur mobile (fait). À re-vérifier visuellement. | Vérifier la barre d'outils FullCalendar (boutons prev/next/today) ne déborde pas. | 🟡 | [ ] |
| **Profil** `/fr/auth/profil/` | tous | G1–G4. `.profile-nav__tab` déborde à droite (317→419 px) — la rangée d'onglets du profil n'est pas contenue. 3,1 écrans. | `.profile-nav` en `overflow-x:auto` (scroll horizontal des onglets) ou onglets en `flex-wrap:wrap`. | 🟢 | [ ] |
| **Tableau de bord formateur** `/fr/dashboard/formateur/` | formateur | G1–G4, G8 (**10 cibles < 44 px** : `.btn-fmt` 37, `.btn-sm` 32, `.fmt-link` 27, checkbox 17). 3,1 écrans. Orbe décoratif clippé (OK, parent `overflow:hidden`). | G8. Vérifier grilles KPI 2 colonnes, `.devoir-row` en carte (fait). | 🟡 | [ ] |
| **Créer / éditer un cours** `/fr/apprentissage/cours/nouveau/`, `.../editer/` | formateur | À auditer (`cours_form.html`). Attendu : labels surdimensionnés, barre d'actions non empilée, vides. | Mise en page formulaire commune (voir §3, Phase 2). | 🟡 | [ ] |
| **Assistant de création (wizard)** `/fr/apprentissage/cours/wizard/...` | formateur | À auditer (5 étapes). Règles `.wizard-nav` ajoutées avant — à re-vérifier. | Boutons `.wizard-nav` empilés pleine largeur ≥ 46 px ; barre de progression lisible. | 🟡 | [ ] |
| **Gérer cours / chapitre** `/fr/apprentissage/.../gerer/` | formateur | Accordéons `.builder-summary` empilés (fait) ; modale `gerer_chapitre` en feuille (fait). À re-vérifier. | Vérifier la feuille modale : dans le viewport, fermeture backdrop/échap. | 🟡 | [ ] |
| **Formulaire d'événement** `/fr/apprentissage/evenement/nouveau/` | formateur | Padding carte réduit (fait, 640→768). À re-vérifier labels + boutons. | Mise en page formulaire commune. | 🟢 | [ ] |
| **Analytics formateur** `/fr/apprentissage/formateur/analytics/` | formateur | Bug media query corrigé (`.analytics-hero`), KPI 2 col, charts `max-width:100%` (fait). À re-vérifier. | Vérifier graphiques `max-width:100%`, pas de débordement. | 🟡 | [ ] |
| **Centre de commandement (admin)** `/fr/dashboard/admin/` | admin | G1–G5. **4,4 écrans** (très long). H1 26 px. Sinon 0 débordement, table OK. | Condenser : marges de section `--m-*`, KPI 2 col, cartes graphiques compactes. Éventuellement replier la timeline. | 🟡 | [ ] |
| **Gestion des utilisateurs** `/fr/auth/gestion/` | admin | G1–G5. 🔴 **55 px de défilement horizontal de PAGE** : la rangée `.admin-filter-btn` (Tous les rôles / Élève / Formateur / Admin) déborde à droite (dernier bouton 376→515 px), non contenue. Table `.admin-table` (sw 765) dans conteneur scrollable, mais bord à 790 → à vérifier que le conteneur ne déborde pas lui-même. | `.admin-filter-*` : `flex-wrap:wrap` **ou** conteneur `overflow-x:auto` + `flex-shrink:0` sur les boutons. Vérifier `.table-container { max-width:100%; overflow-x:auto }` sur la table. | 🟡 | [ ] |
| **Paramètres système** `/fr/auth/gestion/parametres/` | admin | **OK** — 1,3 écran, inputs ≥ 16 px, 0 débordement (input `-9999px` = a11y, normal). | RAS. | 🟢 | [ ] |
| **Logistique — Inventaire / Tickets / Ateliers / Demandes** `/fr/logistics/*` | admin/formateur | G1–G5. Hero sombre + sous-nav pills (Inventaire / Tickets / Ateliers / Demandes) + KPI 2×2 — correct. **5 cibles < 44 px** (pills de sous-nav, « Nouveau ticket »). `.logi-stats` 2 col (fait). | G8 sur les pills de sous-nav ; vérifier tableaux (tickets_list) dans conteneur scrollable + pagination. | 🟡 | [ ] |
| **Carte satellite (point 6 encadrant)** `/fr/dashboard/admin/` (partial) + `apprentissage/partials/satellite_updates_card.html` | admin | Colonne `.sat-row` + `.sat-btn` pleine largeur (fait ≤ 600 px). À re-vérifier après refonte header. | RAS a priori — re-vérifier. | 🟢 | [ ] |

---

## 3. Statut final (2026-08-31)

**Les 4 phases sont exécutées et poussées** (`7070c3c` → `ff469e2`), CSS uniquement,
tout scopé `@media (max-width:768px)`, **desktop vérifié inchangé à 1280 px**,
99 tests verts + `manage.py check` OK à chaque commit.

### Bugs fonctionnels corrigés

| # | Page | Symptôme | Commit |
|---|------|----------|--------|
| 1 | Session socratique | composeur du chat **sous la barre du bas**, bouton « envoyer » coupé | `34e961e` |
| 2 | Gestion des utilisateurs | **47 px de défilement horizontal** de toute la page (`<select>` masqué TomSelect) | `513ec63` |
| 3 | Modale de formulaire long (nouveau chapitre) | bouton « Enregistrer » **coupé hors écran** | `ff469e2` |
| 4 | Dashboard élève | `.radar-panel` débordait | `c221059` (Phase 2) |

### Constats globaux : G1 G2 G3 G7 G8 G9 ✅ · G4 partiel (choix assumé) · G5 faux positif · G6 non fait (priorité basse, sans impact)

### Vérifié en navigateur à 375 px
visiteur (accueil, catalogue, inscription, connexion) · élève (dashboard, catalogue,
détail cours/chapitre, session socratique, notifs, profil, calendrier) · formateur
(dashboard, nouveau cours, gérer cours, wizard, calendrier/événement) · admin
(centre de commandement, gestion utilisateurs, paramètres, logistique inventaire,
carte satellite) · composants (menu latéral, dropdowns notifs+profil, toasts,
bannière PWA, FAB + panneau tuteur, modale).

### Reste — non revérifié individuellement (règles héritées des passes précédentes, pas de régression attendue)
- **QCM** — cartes de questions : besoin d'un LLM ou d'un cache `QuestionCache` chaud pour rendre le corps ; en-tête OK (`2594af7`).
- **Résultats QCM**, **onboarding** (4 étapes), **carnet de notes**, **mes devoirs**, **analytics formateur** : règles mobiles posées lors des passes 2026-08-29/30, non re-capturées cette fois.
- MySQL, vrai téléphone, PWA réelle (secure-context).

### Non fait volontairement
- G4 « tout dans le tiroir » : FR/EN gardé à plat dans le header (moins de risque qu'un déplacement DOM/JS) — à rouvrir si besoin.
- G6 : `.main-nav` fermé reste `display:flex` hors écran (aucun impact).
- Condensation plus poussée du **centre de commandement admin** (4,1 écrans) : contenu dense par nature, repli de la timeline = travail JS non justifié.

---

## 4. Ce qui était déjà correct avant cette refonte (commit `2594af7`)

- Détail chapitre (fil d'Ariane, titre)
- Dropdown de notifications (ancré au viewport)
- En-tête QCM (réagencé)
- Menu latéral off-canvas (`transform: translateX`)
- FullCalendar bascule `listMonth` sur mobile
