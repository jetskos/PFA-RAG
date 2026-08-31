# PLAN_MOBILE.md — Refonte du design mobile (Phase 0 : audit)

> Statut : **audit terminé, en attente de validation avant de coder.**
> Périmètre : responsive < 768 px. Le desktop (≥ 769 px) ne doit pas bouger.
> Méthode : parcours navigateur à 375 px (viewport 375×812), connecté
> successivement en visiteur / élève (`enfant1@smart.com`) / formateur
> (`prof@smart.com`) / admin (`admin@smart.com`), sur la branche
> `finalisation-plateforme` au commit `a1e78c3`, base SQLite de démo.

---

## 1. Constats globaux (présents sur ~toutes les pages)

| ID | Constat | Preuve | Correctif proposé | Risque | Fait |
|----|---------|--------|-------------------|--------|------|
| **G1** | **En-tête sur 2 rangées.** ~~`.brand` est centré (marges auto)~~ **CAUSE RÉELLE : `base.css` `@media (max-width:640px) { .header-inner { flex-direction:column } }`** (bloc hérité). `.header-inner` fait `scrollHeight = 88 px` pour `clientHeight = 48 px`. | toutes les pages | ✅ **FAIT (commit Phase 1)** : bloc 640 px vidé dans base.css ; `responsive.css @≤768px` force `.header-inner { flex-direction:row; min-height:52px }` + `.header-actions { margin:0; flex:0 0 auto }`. Vérifié 375 px (visiteur + élève) : 1 rangée 55 px, `horizScroll:0`, bord droit à 359/375. Desktop 1280 px inchangé. | Faible | [x] |
| **G2** | **`.header-actions` déborde à droite.** Résolu par G1 (une seule rangée, `flex:0 0 auto`, `justify-content:flex-end`). Reste serré : élève = bell+thème+FR/EN+avatar → bord droit 359/375 (16 px de marge). | capture téléphone (inscription) | ✅ **FAIT (Phase 1)** — tient sur 360 px aussi. Marge à surveiller si un 5ᵉ élément apparaît. | Faible | [x] |
| **G3** | **Pastille FR / EN « flottante ».** `.lang-switch-track` = pilule blanche bordée `border-radius:20px` posée sur un en-tête clair → détachée. | toutes les pages | ✅ **FAIT (Phase 1)** : gardée dans l'en-tête mobile mais **à plat** — `.lang-switch-track` fond transparent + sans bordure, bouton actif = texte teal souligné (plus de pilule pleine). Desktop garde la pilule d'origine (règle scopée `@≤768px`). *(choix : gardée en header plutôt que déplacée dans le drawer → moins de risque, pas de modif DOM/JS ; à rediscuter si tu préfères la version drawer.)* | Faible | [x] |
| **G4** | **Navigation dupliquée en 3 exemplaires.** Header (liens nav + connexion / inscription) ⟂ barre du bas (Accueil / Cours / Connexion / Menu) ⟂ menu latéral. Le header refait ce que fait déjà la barre du bas. | toutes les pages | Le header mobile ne porte **aucun lien de navigation ni action d'auth**. Navigation = barre du bas + menu latéral. Connexion / Inscription visiteur = barre du bas (« Connexion ») + CTA dans le contenu. | Moyen — masquer `.main-nav` inline links + boutons auth du header via media query ; s'assurer que tout est bien présent dans le drawer. | [ ] |
| **G5** | ~~Barre du bas admin = 5 items → libellés tronqués~~ **FAUX POSITIF** : vérifié à 375 px, les 5 libellés (« Accueil / Structure / Utilisateurs / Paramètres / Menu ») rendent en entier à 10,4 px, `whiteSpace:normal`, non clippés (`itemW 75 px` > `spanW 57 px`). Le « Utilisateu » de l'audit venait d'un `.slice(0,10)` du script. | — | RAS. Éventuellement `env(safe-area-inset-bottom)` déjà présent. | ✅ rien à faire |
| **G6** | `.main-nav` reste `display:flex` (fixed, hors écran) quand le menu est fermé, au lieu de `display:none`. Ses liens apparaissent dans les audits d'overflow (positions négatives). | toutes les pages | `@media (max-width:768px) { .main-nav:not(.open){ visibility:hidden } }` ou `display:none` + `.open{display:flex}` — sans casser la transition `transform`. | Faible. | [ ] |
| **G7** | **Pas d'échelle d'espacement partagée.** `.site-main` = `padding: 14.4px 12px 16px` (12 px latéral) ; chaque « shell » (`.db-shell`, `.qcm-shell`, `.apprentissage-shell`, `.fmt-wrap`, `.page-shell`…) a son propre padding et ses propres marges de section (1 rem ici, 1.4 rem là, 2.4 rem ailleurs). | comparaison inter-pages | Dans `responsive.css`, en tête du bloc `@media (max-width:768px)` : variables `--m-1..--m-6` + **padding latéral conteneur unique = 1 rem** appliqué à `.site-main` et à tous les shells ; marges de section homogènes. | Moyen — beaucoup de sélecteurs touchés, mais tout en media query, testable page par page. | [ ] |
| **G8** | **Cibles tactiles < 44 px non couvertes.** La règle globale actuelle vise `.btn-primary/.btn-ghost/…` mais pas : `.btn-fmt` (37 px), `.btn-sm` (32 px), `.fmt-link` (27 px), `.admin-filter-btn`, sous-nav logistique, `input[type=checkbox]` (17 px), lien `.brand` (30 px). | dashboard formateur (10 cas), logistique (5), gestion | Étendre la règle globale `min-height:44px` (+ `display:inline-flex; align-items:center`) à ces classes ; checkboxes/radios → 20 px min + zone de tap via le `<label>`. | Faible-moyen — vérifier que ça ne casse pas des barres d'outils denses en desktop (rester en media query). | [ ] |
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

## 3. Rattachement aux 4 phases de la prompt

**Phase 1 — Coquille globale** → G1, G2, G3, G4, G5, G6, G9 + `main` padding-top/bottom via variables (header fixe + barre du bas + safe-area). Un seul commit, bénéficie à **toutes** les pages.

**Phase 2 — Système de design mobile** (`responsive.css`) → G7, G8 :
- variables `--m-1: .25rem … --m-6: 2rem` ;
- padding latéral conteneur unique 1 rem (`.site-main`, tous les `*-shell`, `*-wrap`) ;
- typo : `h1 clamp(1.35rem,5.5vw,1.8rem)`, `h2 clamp(1.15rem,5vw,1.5rem)`, labels `.9rem`, corps `1rem` ;
- règle cibles tactiles étendue (`.btn-fmt/.btn-sm/.fmt-link/.admin-filter-btn/.logi-subnav a/checkbox+label`) ≥ 44 px ;
- vérifier que `input,select,textarea{font-size:16px}` est bien global (constaté OK sur paramètres système) ;
- grilles multi-colonnes → 1 colonne (`minmax(0,1fr)` + `min-width:0`), sauf KPI compacts → 2 ;
- barres d'actions (`form-actions`, `modal-actions`, `wizard-nav`, `page-header-actions`) → empilées pleine largeur.

**Phase 3 — Balayage par famille** (un commit par famille) :
1. **Auth** (register, login, pending, password-reset, onboarding) — vide mort, labels, double logo.
2. **Cours / apprentissage** (catalogue, détail cours, chapitre, notes, devoirs, calendrier) — `.catalog-hero`, cartes.
3. **Tuteur IA** (session socratique 🔴, QCM, résultats).
4. **Dashboards** (élève : radar + cartes rapides ; formateur : G8 ; admin : longueur).
5. **Formulaires formateur** (cours, chapitre, document, événement, wizard, gérer).
6. **Logistique** + **gestion utilisateurs** (`.admin-filter-btn` 🔴) + carte satellite.

**Phase 4 — Composants dynamiques** : menu latéral (fait `transform`), dropdown notifs (fait), dropdown profil (OK), modales (feuille), toasts, bannière PWA, FAB tuteur, sélecteur de langue (après déplacement G3). Tester ouverts à 360 / 375 / 390 px.

---

## 4. Les 5 chantiers les plus impactants

1. **En-tête mobile sur une seule rangée (G1–G3).** Visible sur **100 %** des pages ; aujourd'hui 2 rangées, pastille FR/EN qui « flotte », bouton de connexion coupé par le bord. Fix : `.brand` à gauche, 2 actions maxi à droite, FR/EN + compte descendus dans le menu latéral. → *le correctif le plus rentable, une seule fois pour tout le site.*

2. **Système de design mobile centralisé (G7).** Une échelle d'espacement + des `clamp()` typo + un padding conteneur unique dans `responsive.css`, appliqués à tous les « shells ». → *supprime l'impression « chaque page a été faite par quelqu'un d'autre ».*

3. **Session socratique — l'input passe sous la barre du bas (bug fonctionnel) + ~470 px de chrome avant le chat.** Fix : `padding-bottom` safe-area sur la zone de chat, composeur `sticky`, cartes du haut condensées en une barre compacte.

4. **Règle globale de cibles tactiles étendue (G8).** `.btn-fmt`, `.btn-sm`, `.fmt-link`, filtres admin, pills logistique, checkboxes — aujourd'hui 17–37 px. → *~25 cibles trop petites rien que sur les dashboards formateur/admin.*

5. **Débordements horizontaux ponctuels.** `.admin-filter-btn` (**55 px de scroll-x** sur la gestion des utilisateurs), `.radar-panel` (dashboard élève), `.catalog-hero` (rangée de puces), `.profile-nav__tab`. → *4 corrections ciblées « envelopper / 1 colonne / flex-wrap ».*

---

## 5. Ce qui est déjà correct (ne pas retoucher)

- Détail chapitre (fil d'Ariane, titre) — commit `2594af7`.
- Dropdown de notifications (ancré au viewport) — commit `2594af7`.
- En-tête QCM (réagencé) — commit `2594af7`.
- Menu latéral off-canvas (`transform: translateX`) — commit `2594af7`.
- Paramètres système, dropdown profil, carte satellite (≤ 600 px).
- FullCalendar bascule `listMonth` sur mobile.

---

## Fichier

`versionmobilitoavec/PLAN_MOBILE.md` (racine du repo).

**En attente de ta validation.** Dis-moi : (a) on part sur les 4 phases dans cet
ordre ? (b) pour la barre du bas admin (G5), tu veux garder quels 4 items ?
(c) FR/EN : on la descend dans le menu latéral (recommandé) ou on la garde en
header en version compacte ?
