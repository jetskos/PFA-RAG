# Rapport d'audit — plateforme_educative

Branche `finalisation-plateforme` (`c1c6be6`) · audit du 2026-08-30 · Django 4.2.30 / Python 3.13

> **MÀJ 2026-08-30 — correctifs appliqués.** Tous les bugs P1/P2/P3 de ce rapport
> sont corrigés (voir § « Correctifs appliqués » ci-dessous). Restent volontairement
> non traités : UX-03 (chantier styles inline), UX-05/06/07/08, et le gros nettoyage
> (CLEAN-05/06/09/13/16/18/19 — images mortes, purge `base.css`, partials orphelins).
> `python manage.py test` = **99 verts** (SQLite ; passe MySQL à relancer côté user).

Méthode : 99 tests de référence rejoués (verts), parcours de **toutes** les routes GET
sous 4 rôles (anon / élève / formateur / admin) via le client de test, rendu des
~30 pages clés en FR **et** EN, revue de code ciblée (permissions, i18n, sécurité,
requêtes), inventaire des fichiers statiques et des dépendances.

---

## 1. Résumé exécutif

La plateforme est **fonctionnellement saine** : aucun 500, aucune exception sur
l'ensemble des pages parcourues, le cloisonnement des rôles est globalement correct
(décorateur `role_required` + mixins objet cohérents), l'i18n est à ~99 % propre,
l'inscription ne permet aucune élévation de privilège, les jobs export/import sont
scellés au demandeur.

Il reste **2 trous d'accès** (l'espace formateur ouvert à tout compte connecté ; le
dossier `/media/` servi sans authentification), **1 réglage de déploiement risqué**
(`DEBUG=True` par défaut), **1 fuite i18n visible** (timeline du dashboard admin en
français dur), des **finitions manquantes** (pas de pages 403/404/500, flash de
thème clair, logo de 2,2 Mo) et **~16 Mo de fichiers morts** + une pile REST
entièrement inutilisée à retirer.

**Présentable à l'encadrant ?** → **Oui après les P1/P2.** Les 6 exigences sont
satisfaites sur le fond. Les corrections P1 (SEC-01, SEC-05, I18N-01) sont courtes
(< 1 h cumulée) et éliminent les remarques les plus probables. Les P2 (pages
d'erreur, poids du logo, `/media/`) valent le coup avant la démo.

---

## 2. Tableau de synthèse

| ID | Gravité | Zone | Résumé | Effort |
|----|---------|------|--------|--------|
| SEC-01 | **P1** | Accès / formateur | `espace_formateur` : `@login_required` seul → un élève ouvre l'espace formateur | S |
| SEC-05 | **P1** | Déploiement | `DEBUG` par défaut `True` : un nœud déployé sans `.env` tourne en debug | S |
| I18N-01 | **P1** | i18n / dashboard admin | Timeline d'activité : 6 chaînes FR en dur, restent en français en mode EN | S |
| SEC-02 | P2 | Accès / contenu | `/media/` servi par `static.serve` **sans auth** : PDF, vidéos, ZIP d'export téléchargeables par URL | M |
| BUG-03 | P2 | UX / erreurs | Aucune page 403 / 404 / 500 personnalisée → pages Django brutes en prod | M |
| UX-04 | P2 | Perf / mobile | `logo.png` / `logo_white.png` = **2,2 Mo** chacun, chargés sur chaque page | S |
| SEC-04 | P2 | Config | `ALLOWED_HOSTS` par défaut contient `'*'` | S |
| BUG-04 | P3 | UX / thème | `data-theme="light"` en dur + script en fin de `<body>` → flash blanc en mode sombre | S |
| SEC-03 | P3 | Accès / contenu | `telecharger_document` : tout compte connecté télécharge n'importe quel document (hors niveau) | S |
| SEC-06 | P3 | Sécurité | `Content-Disposition` : `filename` construit avec `document.titre` non échappé | S |
| BUG-05 | P3 | Robustesse | `verifier_statut_qcm` renvoie `en_cours` (200) pour tout `task_id` inconnu | S |
| BUG-06 | P3 | Cosmétique | `activate_pending_student_view` renvoie 403 (au lieu de 405) sur GET | S |
| BUG-07 | P3 | Code mort | `detail_cours` : bloc `if settings.DEBUG:` qui calcule des variables jamais utilisées | S |
| BUG-08 | P3 | Fuite d'info | export/import : `except Exception as e … str(e)` renvoyé au client (500) | S |
| I18N-02 | P3 | i18n | `base.html` : `aria-label="Menu"`, `title="Notifications"`, `alt="Photo de profil"` en dur | S |
| UX-03 | P3 | Design | `style="…"` en ligne massif (espace_formateur 91, detail_chapitre 56, …) | L |
| UX-05 | P3 | Perf | `tom-select` (51 Ko JS) chargé globalement, utilisé sur ~4 pages ; auto-init sur tout `<select>` | M |
| UX-07 | P3 | Produit | Le catalogue exige une connexion (choix à confirmer) | S |
| UX-08 | P3 | PWA | Auto-`reload()` au changement de service worker : coupe l'utilisateur en pleine saisie | S |

Nettoyage → section 4 (CLEAN-01 à CLEAN-20).

---

## 3. Détail des constats

### SEC-01 — `espace_formateur` accessible à tout utilisateur connecté  ·  **P1**  ·  CONFIRMÉ
- [ ] **Fichier** : `plateforme_educative/apprentissage/views.py:96-118`
- **Repro** : se connecter en élève (`enfant1@smart.com / enfant123`), ouvrir
  `/fr/apprentissage/formateur/` → **HTTP 200**, la page « Espace formateur »
  s'affiche (listes vides, mais UI « Créer un cours / Exporter / Importer / Devoirs à
  noter » visible). Toutes les autres vues formateur (`gerer_cours`, `nouveau_cours`,
  `devoir_creer`…) renvoient bien 403 pour l'élève.
- **Observé** : `@login_required` seul, aucun contrôle de rôle. Le docstring de
  `apprentissage/mixins.py:7` affirme pourtant « espace_formateur : OK (vérifie le
  rôle FORMATEUR) » → commentaire faux.
- **Attendu** : 403 pour un élève, comme les autres pages `formateur/`.
- **Correctif** : ajouter le garde de rôle. Le plus simple, cohérent avec le reste :
  ```python
  from core.views import role_required
  # ...
  @role_required('FORMATEUR')          # superuser + ADMIN passent déjà
  def espace_formateur(request):
  ```
  (ou un test inline `if not request.user.is_formateur and request.user.role != 'ADMIN': return HttpResponseForbidden(...)`).
  Corriger aussi le docstring `mixins.py:7`.
- **Risque** : faible. Vérifier que l'admin (`role='ADMIN'`) garde l'accès (il l'a via
  le `or ADMIN`). `role_required` importe depuis `core.views` → pas de cycle
  d'import (core.views n'importe pas apprentissage.views).
- **Test** : ajouter à `apprentissage/tests/test_permissions.py` un cas
  `eleve → /apprentissage/formateur/ == 403`. Rejouer `python manage.py test`.

### SEC-05 — `DEBUG` vaut `True` par défaut  ·  **P1**  ·  CONFIRMÉ
- [ ] **Fichier** : `plateforme_educative/core/settings.py:35`
- **Observé** : `DEBUG = os.getenv('DJANGO_DEBUG', 'True')…`. Un nœud satellite
  déployé sans fichier `.env` complet démarre en **debug** : tracebacks complets
  exposés, `SECURE_*`/HSTS désactivés (bloc `if not DEBUG`), `ALLOWED_HOSTS` laxiste.
  Le `SECRET_KEY` a un garde-fou prod (`raise ValueError` si `django-insecure-`),
  mais rien n'empêche `DEBUG=True` en production.
- **Attendu** : défaut sûr (`False`), le développeur active explicitement le debug.
- **Correctif** : `DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in {...}` et
  documenter `DJANGO_DEBUG=True` dans le `.env` de dev + `test_local.sh` (qui le
  positionne déjà). Vérifier que `test_local.sh` exporte bien `DJANGO_DEBUG=True`
  (c'est le cas, ligne « export DJANGO_DEBUG=True »).
- **Risque** : moyen — en prod, `DEBUG=False` impose `ALLOWED_HOSTS` correct et
  `collectstatic` fait (déjà requis). Tester un `runserver` local avec
  `DJANGO_DEBUG=False DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost` + `collectstatic`.
- **Test** : `python manage.py check --deploy` avant/après ; la suite reste verte
  (le bloc test force déjà son propre `STATICFILES_STORAGE`).

### I18N-01 — Timeline du dashboard admin en français dur  ·  **P1**  ·  CONFIRMÉ
- [ ] **Fichier** : `plateforme_educative/core/views.py:56-84`
  (titres l. 60, 71, 82 ; descriptions f-string l. 61, 72, 83)
- **Repro** : se connecter en admin, basculer en EN, ouvrir `/en/dashboard/admin/` →
  le fil « Activité récente » affiche « Nouvel utilisateur inscrit », « Cours
  publié », « Nouveau ticket matériel ouvert » et « L'utilisateur X a créé son
  compte. » en **français**.
- **Observé** : chaînes non enveloppées dans `gettext`, et descriptions en
  f-string (interpolation ⇒ non traduisible telle quelle).
- **Correctif** :
  ```python
  from django.utils.translation import gettext as _
  # titre
  'title': _("New user registered"),
  # desc : passer en gettext + placeholders nommés
  'desc': _("%(name)s created their account.") % {'name': u.get_full_name()},
  'desc': _("The module '%(title)s' was published for level %(level)s.")
          % {'title': c.titre, 'level': c.niveau.nom},
  'desc': _("Trainer %(name)s reported a need for %(item)s.")
          % {'name': t.formateur.get_full_name(),
             'item': t.equipement.nom if t.equipement else _('equipment')},
  ```
- **Risque** : faible. `_admin_dashboard_context` est aussi appelé hors requête
  (`request=None`) ; `gettext` (non lazy) est sûr ici car le rendu se fait dans une
  requête. Après ajout : `makemessages -l en --no-wrap --no-obsolete` puis
  `compilemessages -l en` et traduire les ~6 nouvelles entrées. **Ne pas** lancer
  `makemessages -l fr`.
- **Test** : rendre `/en/dashboard/admin/`, vérifier l'absence de « inscrit / publié /
  matériel ». Suite verte.

---

### SEC-02 — `/media/` servi sans authentification  ·  P2  ·  CONFIRMÉ
- [ ] **Fichier** : `plateforme_educative/core/urls.py:90-94`
- **Observé** : `re_path(r'^media/(?P<path>.*)$', serve, {'document_root': MEDIA_ROOT})`
  ajouté **inconditionnellement** (pas de `if settings.DEBUG`). `django.views.static.serve`
  n'applique aucune authentification. Tout ce qui est sous `MEDIA_ROOT` est
  téléchargeable par n'importe qui connaissant/devinant le chemin :
  `media/documents/AAAA/MM/*.pdf` (supports de cours), vidéos hors-ligne,
  `media/exports/*.zip` (exports de cours complets), `media/imports/temp/*`,
  photos de profil. `telecharger_document` est `@login_required` mais `/media/`
  court-circuite complètement cette vue.
- **Attendu** : sur une plateforme à accès contrôlé, les médias sensibles passent
  par une vue qui vérifie la session (et idéalement le niveau/l'inscription).
- **Correctif** (selon la cible) :
  - **nœud LAN mono-poste hors-ligne** : risque réel faible ; a minima restreindre
    le `serve` à `if settings.DEBUG` et documenter que la prod doit passer par le
    serveur front (nginx) avec `X-Accel` / `internal`.
  - **sinon** : garder une vue protégée `media_protegee(request, path)` avec
    `@login_required`, `FileResponse`, et validation `path` (pas de `..`). Laisser
    `/media/` public **uniquement** pour les sous-dossiers réellement publics
    (ex. images de cartes de cours).
- **Risque** : moyen — casser l'affichage des photos/vidéos si la vue protégée est
  mal branchée. Tester : PDF, photo de profil, vidéo, en connecté et en anonyme.

### BUG-03 — Aucune page d'erreur 403 / 404 / 500  ·  P2  ·  CONFIRMÉ
- [ ] **Fichiers** : absents — aucun `templates/403.html`, `404.html`, `500.html`,
  aucun `handler404/handler500` dans `core/urls.py`.
- **Observé** : en prod (`DEBUG=False`), un lien mort ou une `PermissionDenied`
  (levée en masse par les mixins) affiche la page Django brute non stylée
  (« Not Found », « Server Error (500) », « 403 Forbidden »).
- **Correctif** : créer `core/templates/{403,404,500}.html` étendant `base.html`
  (500 doit être autonome — pas de contexte, pas de tags coûteux), avec un bouton
  retour. Django les prend automatiquement quand `DEBUG=False`.
- **Risque** : nul. Vérifier le rendu de `500.html` sans `request` (pas de
  `{% url %}` vers des vues qui exigent l'auth ; utiliser des liens en dur `/`).
- **Test** : `DEBUG=False` + visiter une URL bidon → 404 stylée ; forcer une
  `PermissionDenied` → 403 stylée.

### UX-04 — Logo de 2,2 Mo chargé partout  ·  P2  ·  CONFIRMÉ
- [ ] **Fichiers** : `plateforme_educative/static/images/logo_white.png` (2,21 Mo,
  chargé dans `base.html:56` sur **toutes** les pages), `static/images/logo.png`
  (2,21 Mo, page d'accueil).
- **Observé** : PNG non optimisés. Sur mobile / hors-ligne (points 3 et 5 de
  l'encadrant), 2,2 Mo par chargement de page pour un logo est disproportionné.
- **Correctif** : ré-exporter en PNG optimisé (`< 60 Ko`, largeur ~300 px @2x) ou
  en SVG. Idéalement une variante `icon-192.png` (déjà présente) sert déjà la
  version mobile.
- **Risque** : nul (remplacement d'asset). Vérifier le rendu header desktop +
  accueil.

### SEC-04 — `ALLOWED_HOSTS` contient `'*'` par défaut  ·  P2  ·  CONFIRMÉ
- [ ] **Fichier** : `plateforme_educative/core/settings.py:45`
- **Observé** : `_env_list('DJANGO_ALLOWED_HOSTS', ['127.0.0.1', 'localhost', '*'])`.
  Combiné à SEC-05, un déploiement sans env = hôtes grands ouverts.
- **Correctif** : retirer `'*'` du défaut. Pour l'accès téléphone en LAN, le nœud
  passe `DJANGO_ALLOWED_HOSTS=<ip-lan>,localhost,127.0.0.1` (ou `DEBUG=True` en
  dev qui rend `ALLOWED_HOSTS` permissif). `test_local.sh` peut exporter l'IP LAN
  détectée.
- **Risque** : faible ; peut bloquer l'accès téléphone si l'IP n'est pas listée →
  documenter.

---

### BUG-04 — Flash de thème clair (FOUC)  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `core/templates/base.html:4` (`data-theme="light"` en dur) +
  script thème `base.html:299-326` (fin de `<body>`).
- **Observé** : le HTML arrive avec `data-theme="light"` ; le script qui lit
  `localStorage.theme` et applique `dark` ne s'exécute qu'en fin de page → les
  utilisateurs en mode sombre voient un flash blanc à **chaque** navigation.
- **Correctif** : script bloquant minimal dans le `<head>`, avant tout rendu :
  ```html
  <script>try{var t=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');document.documentElement.setAttribute('data-theme',t);}catch(e){}</script>
  ```
  et retirer `data-theme="light"` de la balise `<html>` (ou le laisser comme
  fallback). Garder le reste du script thème pour le bouton toggle.
- **Risque** : nul. Tester bascule clair/sombre + rechargement.

### SEC-03 — Téléchargement de document non restreint au niveau  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views.py:662-675`
- **Observé** : `telecharger_document` est `@login_required` mais ne vérifie ni le
  niveau de l'élève ni son inscription au cours → un élève télécharge le PDF d'un
  cours d'un autre niveau s'il connaît l'`id` du document. `detail_cours`
  (l. 492-496) fait ce contrôle, `detail_chapitre` (l. 596-604) et
  `telecharger_document` **non** (incohérence).
- **Correctif** : factoriser un helper `_eleve_peut_voir_cours(user, cours)` et
  l'appliquer dans `telecharger_document` **et** `detail_chapitre`.
- **Risque** : faible ; bien laisser passer formateurs/admins.

### SEC-06 — En-tête `Content-Disposition` non échappé  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views.py:674`
- **Observé** : `f'attachment; filename="{document.titre}.pdf"'` — `document.titre`
  (saisi par le formateur, 255 car.) peut contenir `"` ou des caractères non-ASCII
  → nom de fichier cassé, voire injection d'en-tête (Django bloque les `\n` depuis
  3.2, pas les `"`).
- **Correctif** : `from django.utils.encoding import ...` ou plus simple :
  ```python
  from django.http import FileResponse
  return FileResponse(document.fichier_pdf.open('rb'), as_attachment=True,
                      filename=f"{document.titre}.pdf")
  ```
  (`FileResponse` encode proprement `filename*`). Bonus : ne charge plus tout le
  PDF en mémoire (`.read()`).
- **Risque** : faible. Tester un titre avec accents + guillemets.

### BUG-05 — `verifier_statut_qcm` : 200 pour un task_id inconnu  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `tuteur_ia/views_qcm.py:455-486`
- **Observé** : `AsyncResult(<n'importe quoi>).state == 'PENDING'` →
  `{"status": "en_cours"}` HTTP 200. Un front qui poll sur un mauvais id boucle
  indéfiniment. (Impact limité aujourd'hui : `qcm.html` ne poll pas — un seul
  `fetch` bloquant + le cache pré-chauffé via `warmup_qcm`.)
- **Correctif** : borner le polling côté client (N tentatives) **ou**, si le
  polling n'est plus utilisé, supprimer `verifier_statut_qcm` + sa route + le test
  associé (voir CLEAN-16b).
- **Risque** : faible.

### BUG-06 — 403 au lieu de 405 sur GET  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `core/views.py:674-676` (`activate_pending_student_view`)
- **Observé** : `@require_http_methods(['GET','POST'])` puis
  `if request.method != 'POST': return HttpResponseForbidden('Méthode non autorisée.')`
  → 403 (sémantiquement faux).
- **Correctif** : `from django.http import HttpResponseNotAllowed` →
  `return HttpResponseNotAllowed(['POST'])`, ou retirer `'GET'` du
  `require_http_methods` et supprimer le `if`.
- **Risque** : nul.

### BUG-07 — Bloc DEBUG mort dans `detail_cours`  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views.py:512-519`
- **Observé** : sous `if settings.DEBUG:`, calcul de `file_exists` / `file_path`
  (avec un `os.path.exists` par document !) — variables **jamais lues** ensuite.
- **Correctif** : supprimer le bloc (5 lignes). Retire au passage un accès disque
  par document en dev.
- **Risque** : nul.

### BUG-08 — Fuite d'exception dans export/import  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `apprentissage/views.py:1536-1537` (import) et bloc équivalent
  `export_multiple_courses_view` (~l. 1478-1481)
- **Observé** : `except Exception as e: return JsonResponse({'message': str(e)}, status=500)`
  → message d'exception interne renvoyé au client.
- **Correctif** : logger l'exception, renvoyer un message générique traduit
  (`_("Une erreur est survenue pendant l'import.")`).
- **Risque** : nul (le front affiche déjà `data.message` — rester une string).

### I18N-02 — Attributs en dur dans `base.html`  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `core/templates/base.html:51` (`aria-label="Menu"`),
  `:135` (`title="Notifications"`), `:240` (`alt="Photo de profil"`)
- **Correctif** : `aria-label="{% trans 'Menu' %}"`, etc.
- **Risque** : nul.

### UX-03 — Styles en ligne omniprésents  ·  P3  ·  HYPOTHÈSE (dette, pas un bug)
- [ ] **Fichiers** : `apprentissage/templates/.../espace_formateur.html` (91×
  `style="…"`), `partials/detail_chapitre.html` (56×), `devoirs_liste.html` (53×),
  `logistics/.../demande_form.html` (39×)… + gros blocs conditionnels inline dans
  `base.html` (sélecteur de langue l. 206-217, bannière PWA l. 500-525).
- **Observé** : styles répétés, en conflit avec la cascade des 6 fichiers CSS,
  difficiles à maintenir cohérents (thème sombre notamment).
- **Correctif** : chantier progressif — extraire les motifs récurrents en classes
  utilitaires dans `components.css`. À faire fichier par fichier, hors P1/P2.
- **Risque** : moyen si fait en masse (régressions visuelles) → petit lot par PR.

### UX-05 — `tom-select` chargé globalement  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `base.html:29` (CSS), `:39` (JS 51 Ko), `:334-345`
  (`initSelects` transforme **tout** `<select>` de **toute** page).
- **Observé** : utilisé réellement sur ~4 écrans (admin_dashboard, modales
  logistique). Ailleurs c'est du poids mort + un composant JS greffé sur des
  `<select>` natifs (calendrier, filtres) qui pourrait gêner (clavier mobile,
  `matchMedia`).
- **Correctif** : charger `tom-select` + appeler `initSelects()` seulement sur les
  templates concernés (block `{% block extra_js %}`), ou cibler
  `document.querySelectorAll('select[data-enhance]')`.
- **Risque** : moyen — vérifier que les selects « enrichis » actuels gardent le
  comportement (création désactivée : `{create:false}`).

### UX-07 — Catalogue derrière l'authentification  ·  P3  ·  CONFIRMÉ (choix produit)
- [ ] **Fichier** : `apprentissage/views.py:416` (`@login_required` sur `liste_cours`)
- **Observé** : `/apprentissage/` renvoie 302 → login pour un visiteur.
- **Question** : voulu (plateforme fermée) ? Si l'encadrant s'attend à parcourir
  les cours sans compte, retirer `@login_required` de `liste_cours` **et**
  `detail_cours` en filtrant sur `actif=True` pour l'anonyme.
- **Risque** : faible ; décision à prendre, pas un défaut.

### UX-08 — Rechargement auto au changement de SW  ·  P3  ·  CONFIRMÉ
- [ ] **Fichier** : `core/templates/base.html:544-549` + `service-worker.js`
  (`SKIP_WAITING`).
- **Observé** : `controllerchange` → `window.location.reload()` : si une nouvelle
  version du SW s'active pendant que l'utilisateur remplit un formulaire, la page
  se recharge et la saisie est perdue.
- **Correctif** : ne recharger que si aucun formulaire n'est « sale », ou afficher
  un bandeau « Nouvelle version — recharger » au lieu d'un reload forcé.
- **Risque** : faible.

---

## 4. Nettoyage / optimisation

| ID | Élément | Preuve d'inutilité | Gain | Risque | |
|----|---------|--------------------|------|--------|-|
| CLEAN-01 | Pile **Django REST Framework** : `rest_framework`, `rest_framework.authtoken`, `rest_framework_simplejwt` (`core/settings.py:63-65`), blocs `REST_FRAMEWORK` + `SIMPLE_JWT` (`:194-211`), deps `djangorestframework`, `djangorestframework-simplejwt` | `grep -rn "rest_framework\|simplejwt\|APIView\|Serializer\|api_view" --include=*.py` hors settings/tests → **0 résultat** (seul hit = `JsonPlusSerializer` de LangGraph, sans rapport). Aucune route `/api/`. | -3 apps au boot, -1 table `authtoken_token`, -2 deps, surface d'auth JWT supprimée | Faible — retirer aussi la migration `authtoken` du plan (`migrate` sur base fraîche : ne plus l'inclure). Rejouer les 99 tests. | [ ] |
| CLEAN-02 | `django-cors-headers` dans `requirements.txt` | Absent de `INSTALLED_APPS` / `MIDDLEWARE` ; `grep -rn "cors\|CORS"` → 0 | -1 dep | Nul | [ ] |
| CLEAN-03 | `requirements.txt:2` : `Django>=5.0,<6.0` | Le code tourne et est testé sur **4.2.30** (patterns 4.2). Un `pip install -r` neuf installe Django 5.x → risque de casse silencieuse. | Install reproductible | Faible mais **à faire** : `Django>=4.2,<5.0` | [ ] |
| CLEAN-04 | `reportlab` **absent** de `requirements.txt` | Importé par `seed_demo.py` et `seed_english_course.py` (`_make_pdf`). `pip show reportlab` → installé localement seulement. | Fresh install fonctionnel (points 2 et 4 de l'encadrant) | Nul — **ajouter** `reportlab>=4.0` | [ ] |
| CLEAN-05 | Dossier `plateforme_educative/core/static/` (12 images, ~5 Mo dont 8 `.avif` unsplash) | `core` **n'est pas** dans `INSTALLED_APPS` → `AppDirectoriesFinder` ne le regarde jamais. `python manage.py findstatic core/images/catalog-bg.jpg` → « No matching file found ». | ~5 Mo repo | Nul (jamais servi) | [ ] |
| CLEAN-06 | `static/images/` : 21 images jamais référencées = **10,05 Mo** (`michael-fortsch…unsplash.jpg` 3,9 Mo, `admin_bg.jpg` 1,4 Mo, `aryan-nikhil…jpg` 1,4 Mo, `icon_{ai_tutor,courses,iot,workshop}_generated.png` ~2,3 Mo, `conceptartist-leeb…png` 665 Ko, 7 `.avif`, `pngtree…`, `57d2c4e…`, …) | Script de diff refs↔fichiers (templates + CSS + PY, hash-insensible) : 0 référence. Liste complète en annexe A. | ~10 Mo repo + collectstatic | Faible — vérifier l'accueil après suppression (fait : les images utilisées par `home.html` **sont** référencées et conservées) | [ ] |
| CLEAN-07 | `plateforme_educative/fix_models.py` | Script one-shot, chemin en dur `d:/stage-lms/plateforme_educative/…` (autre machine), remplace un `model_name` qui n'existe plus. | — | Nul | [ ] |
| CLEAN-08 | `plateforme_educative/implementation_plan.md` | 1 ligne, encodage UTF-16 corrompu (« Plan d'Am�lioration »). Stub. | — | Nul | [ ] |
| CLEAN-09 | `static/vendor/tabler-icons/fonts/tabler-icons.woff` (794 Ko) | `tabler-icons.min.css` déclare `woff2` **et** `woff` ; tout navigateur cible supporte woff2 → le `.woff` n'est jamais téléchargé. | 794 Ko repo + collectstatic | Faible — retirer aussi la ligne `url(...woff)` du CSS. Tester l'affichage des icônes. | [ ] |
| CLEAN-10 | `logo.png` / `logo_white.png` 2,2 Mo (= UX-04) | PNG non compressés. | ~4 Mo repo + perf | Nul (ré-export) | [ ] |
| CLEAN-11 | `CSRF_TRUSTED_ORIGINS` en dur `settings.py:47-51` (`*.up.railway.app`, `edutech1.up.railway.app`) | Hébergement Railway abandonné (cible = nœud satellite hors-ligne). | Config plus claire | Nul — garder uniquement le `_env_list('DJANGO_CSRF_TRUSTED_ORIGINS', [])` | [ ] |
| CLEAN-12 | Double implémentation de la détection réseau : `core/utils.has_internet` (8.8.8.8:53) vs `tuteur_ia/agents/llm_factory._has_internet` (api.groq.com:443) | Deux fonctions, deux caches, deux endpoints, même but. | -1 fonction, comportement homogène | Faible — faire pointer `_has_internet` sur `core.utils.has_internet` | [ ] |
| CLEAN-13 | `static/core/css/base.css` : **5228 lignes / 117 Ko**, règles dupliquées (ex. `background-image` identiques l. 863 & 4416, l. 1090 & 4412) | Taille anormale pour du CSS écrit à la main sans framework ; doublons visibles. | Poids CSS sur **chaque** page | **Moyen/élevé** — purge à faire avec couverture (rendre toutes les pages, comparer). **Chantier séparé, pas avant la démo.** | [ ] |
| CLEAN-14 | `apprentissage/tasks.py` : 7 `print()` avec emoji (l. 23, 82, 183, 198, 346, 360, 416) | `logger` existe déjà dans le module. `print("…🚀…")` lève `UnicodeEncodeError` sur console cp1252 sans `PYTHONUTF8`. | Logs propres, pas de crash console | Faible — remplacer par `logger.info(...)` sans emoji | [ ] |
| CLEAN-15 | Bloc DEBUG mort `detail_cours` (= BUG-07) | Variables jamais lues. | -5 lignes, -1 accès disque/doc | Nul | [ ] |
| CLEAN-16a | Partials peut-être orphelins : `accounts/partials/users_table_body.html`, `core/partials/equipements_section.html`, `core/partials/kanban_assignation_section.html`, `logistics/partials/ticket_form_modal.html` | Aucun `include`/`render` littéral trouvé (grep). **À confirmer** : un `{% include %}` peut utiliser une variable. | Templates en moins | Moyen — **vérifier manuellement** chaque un avant suppression | [ ] |
| CLEAN-16b | `verifier_statut_qcm` + route `qcm/statut/<task_id>/` + branche `generer_qcm_task.delay` non câblée | `qcm.html` ne poll pas (voir BUG-05). L'async ne peut pas fonctionner en mode `CELERY_TASK_ALWAYS_EAGER` (pas de result backend). | -1 vue, -1 route, cohérence | Moyen — garder si un déploiement Redis+worker est prévu ; sinon supprimer avec le test `test_new_tasks` associé | [ ] |
| CLEAN-17 | `core/urls.py:26` : `from django.conf.urls.static import static` | Import jamais utilisé (le service média passe par `re_path` + `serve`). | -1 ligne | Nul | [ ] |
| CLEAN-18 | `docs/schema.sql` (6,8 Ko) | SQL figé — probablement désynchronisé des migrations. | Confusion en moins | Faible — vérifier vs `sqlmigrate`, sinon supprimer ou marquer « obsolète » | [ ] |
| CLEAN-19 | `TODO.md` | Décrit l'étape « async indexation PDF » avec une référence de ligne fausse (« vers la ligne 188 »). | Doc juste | Nul — fusionner dans `DEPLOYMENT_README.md` §Celery ou mettre à jour | [ ] |
| CLEAN-20 | Gardes morts `if request.user.is_authenticated:` dans des vues déjà `@login_required` (`detail_chapitre:606,632`, `detail_cours:551`…) | `@login_required` garantit déjà l'authentification. | Lisibilité | Nul | [ ] |

**Migrations** : 10 / 11 / 4 / 10 par app — pas excessif. Un `squashmigrations`
(surtout `tuteur_ia`, qui porte un `0006` réécrit + un `0008_merge`) est possible
mais **risqué** sur des bases déjà déployées → à ne faire que si aucune instance
n'est en production. Non recommandé maintenant.

---

## 5. Non vérifié (à faire manuellement / avec l'environnement complet)

| Sujet | Pourquoi non couvert |
|-------|----------------------|
| **Test sur vrai téléphone** (375 px, gestes, safe-area, clavier) | Cet audit = client de test Django + revue de code. Pas de rendu navigateur 375 px cette passe. → refaire la passe visuelle du prompt UX précédent. |
| **PWA réelle** : install, mode hors-ligne (couper le réseau), page `/offline/`, non-fuite de cache entre comptes | Le service worker exige un contexte sécurisé ; le navigateur intégré ne le teste pas de façon fiable. → tester via `serve_https.py` sur téléphone. |
| **Chaînes IA** : qualité du tuteur socratique, génération QCM de bout en bout | Aucun Ollama lancé dans l'environnement d'audit. Seul le chemin de **dégradation** (503 traduit, pas de 500) est confirmé sur toutes les routes IA. |
| **Lecture vidéo HLS** | Aucune vidéo encodée dans le jeu de démo. |
| **Export → import round-trip avec vrai contenu** | Seuls les codes de permission ont été vérifiés ici. La mécanique est couverte par `apprentissage/tests/test_satellite.py` + la revue de code précédente. |
| **Django `/admin/` pages profondes** | Codes de permission OK (302/403 attendus) ; contenu non parcouru en détail. |
| **Accessibilité** (lecteur d'écran, axe-core, contraste mesuré) | Inspection de code seulement : focus visible et labels globalement présents, quelques `aria-label` FR en dur (I18N-02). |
| **Comportement à l'échelle** | Dashboard admin = 29 requêtes avec un mini jeu de données ; pas de test avec 500 élèves / 100 cours. |
| **`DEBUG=False` de bout en bout** | `check --deploy` non lancé ; à faire après SEC-05. |

---

## 6. Ordre de correction recommandé

**Lot 1 — avant la démo encadrant (P1, ~1 h)**
1. **SEC-01** — garde de rôle sur `espace_formateur` (+ corriger le docstring `mixins.py`). Indépendant.
2. **I18N-01** — timeline dashboard admin en `gettext` + `makemessages -l en` / `compilemessages -l en` + traduction des ~6 entrées. Indépendant.
3. **SEC-05** — `DEBUG` défaut `False` ; vérifier `test_local.sh` (déjà OK) et documenter `.env`. **Dépend de** : rien, mais **faire SEC-04 dans la foulée** (retirer `'*'` d'`ALLOWED_HOSTS`) car les deux vont ensemble pour un déploiement sain.
4. Rejouer `python manage.py test` (99 verts) + `python manage.py check --deploy`.

**Lot 2 — finitions visibles (P2, ~2-3 h)**
5. **BUG-03** — pages `403/404/500.html`. Indépendant.
6. **UX-04 / CLEAN-10** — ré-export des logos < 60 Ko. Indépendant.
7. **SEC-02** — décision `/media/` : `if settings.DEBUG` sur le `serve` + doc nginx (option nœud LAN) **ou** vue protégée. **Dépend de** la cible de déploiement — à trancher avec toi.
8. **BUG-04** — script thème inline dans le `<head>`. Indépendant.

**Lot 3 — nettoyage (P3, faisable en une passe, ~2 h)**
9. CLEAN-01 (DRF), CLEAN-02 (cors), CLEAN-03 (pin Django), CLEAN-04 (reportlab),
   CLEAN-05 (`core/static/`), CLEAN-06 (10 Mo d'images), CLEAN-07 (`fix_models.py`),
   CLEAN-08 (`implementation_plan.md`), CLEAN-11 (Railway), CLEAN-17, CLEAN-20.
   → un seul commit « nettoyage », rejouer les tests + `collectstatic` + rendre
   l'accueil.
10. CLEAN-09 (woff), CLEAN-12 (has_internet), CLEAN-14 (print→logger), CLEAN-15,
    CLEAN-19. Indépendants.
11. **BUG-05 / CLEAN-16b** — trancher le sort de l'async QCM (garder pour Redis, ou
    supprimer vue + route + test). **Dépend d'**une décision d'archi.

**Lot 4 — chantiers séparés (ne pas mélanger)**
12. **UX-03** (styles inline → classes) : petit lot par domaine.
13. **CLEAN-13** (purge `base.css`) : nécessite une couverture visuelle complète.
14. **CLEAN-16a** (partials orphelins) : confirmer un par un.
15. Reprendre les points « Non vérifié » (téléphone réel, PWA, IA avec Ollama).

---

## Correctifs appliqués (2026-08-30)

| ID | Correctif |
|----|-----------|
| SEC-01 | `espace_formateur` : `raise PermissionDenied` si non formateur/admin. Docstring `mixins.py` corrigé. Vérifié : élève → 403. |
| SEC-05 | `DEBUG` défaut `False`. `_TESTING` exclut la suite de tests du durcissement prod. La clé `django-insecure-` n'est plus servie en prod : clé aléatoire éphémère + `RuntimeWarning` (au lieu d'un `raise` qui cassait toutes les commandes `manage.py`). |
| I18N-01 | Timeline dashboard admin : `gettext_lazy` + placeholders nommés (plus de f-strings). 18 entrées EN ajoutées à `django.po` (diff chirurgical de 59 lignes, `makemessages` non relancé pour éviter la réécriture massive). Vérifié : `/en/dashboard/admin/` sans fuite FR. |
| SEC-02 | `/media/` passe par `core/protected_media.serve_protected_media` (`@login_required` + blocage `chroma_db/ imports/ satellite_inbox/`). Vérifié : anon → 302, connecté → 200, `chroma_db` → 404. |
| SEC-04 | `ALLOWED_HOSTS` : `['*']` seulement si `DEBUG`, sinon `['127.0.0.1', 'localhost']`. `DJANGO_SECURE_SSL_REDIRECT` rendu configurable (nœud LAN HTTP). |
| SEC-03 | Helper `_eleve_peut_acceder_cours()` appliqué à `detail_chapitre` **et** `telecharger_document`. |
| SEC-06 | `telecharger_document` : `FileResponse(as_attachment=True, filename=…)` — encodage correct + plus de `.read()` en mémoire. |
| BUG-03 | `core/templates/{403,404,500}.html` créés (404/403 étendent `base.html`, 500 autonome bilingue). `role_required` lève désormais `PermissionDenied` → la page 403 stylée s'affiche. |
| BUG-04 | Script thème inline bloquant dans le `<head>` de `base.html` (plus de flash clair en mode sombre). |
| BUG-05 | `verifier_statut_qcm` : valide que `task_id` est un UUID → 404 sinon (plus de boucle infinie côté client). `str(e)` d'exception ne fuit plus. |
| BUG-06 | `activate_pending_student_view` : `@require_http_methods(['POST'])` → 405 sur GET. |
| BUG-07 | Bloc `if settings.DEBUG:` mort supprimé de `detail_cours`. |
| BUG-08 | export/import : exception `logger.exception` + message générique traduit (plus de `str(e)` au client). |
| I18N-02 | `base.html` : `aria-label`/`title`/`alt` passés en `{% trans %}`. |
| CLEAN-01/02 | DRF + SimpleJWT + authtoken retirés de `INSTALLED_APPS` et `settings` ; `djangorestframework*`, `django-cors-headers` retirés de `requirements.txt`. |
| CLEAN-03 | `requirements.txt` : `Django>=4.2,<5.0`. |
| CLEAN-04 | `reportlab>=4.0` ajouté à `requirements.txt`. |
| CLEAN-07/08 | `fix_models.py` et `implementation_plan.md` supprimés. |
| CLEAN-14 | 7 `print()` de `apprentissage/tasks.py` → `logger.info` (sans emoji ; plus de risque `UnicodeEncodeError` cp1252). |
| CLEAN-17 | Imports morts retirés de `core/urls.py`. |
| CLEAN-20 | Gardes `if request.user.is_authenticated` morts retirés de `detail_chapitre`. |

À faire côté user : relancer `python manage.py test` sous MySQL (service arrêté ici,
démarrage impossible sans élévation) ; `python -m pip install -r requirements.txt`
pour purger les paquets DRF de l'environnement.

## Annexe A — 21 images orphelines de `static/images/` (10,05 Mo)

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
(vérifier une dernière fois `home.html` + `base.css` avant `git rm`.)

## Annexe B — carte des permissions (extrait, préfixe `/fr/`)

| Route | anon | élève | formateur | admin |
|-------|:---:|:---:|:---:|:---:|
| `apprentissage/formateur/` (`espace_formateur`) | 302 | **200 ⚠ SEC-01** | 200 | 200 |
| `apprentissage/formateur/cours/nouveau/` | 302 | 403 | 200 | 200 |
| `apprentissage/formateur/notes/` | 302 | 403 | 200 | 200 |
| `apprentissage/admin/analytics/` | 302 | 403 | 403 | 200 |
| `apprentissage/satellite/card/` | 302 | 403 | 403 | 200 |
| `dashboard/admin/` | 302 | 403 | 403 | 200 |
| `dashboard/formateur/` | 302 | 403 | 200 | 200 |
| `dashboard/student/` | 302 | 200 | 403 | 200 |
| `auth/gestion/` (`admin_dashboard`) | 302 | 302→login | 302→login | 200 |
| `logistics/` (`inventaire`) | 302 | 302 | 302 | 200 |
| `tuteur/qcm/<id>/generer-api/` | 302 | 503* | 503* | 503* |

\* 503 = dégradation propre « moteur IA indisponible » (pas de 500) — attendu sans Ollama.
Aucun 500 ni exception sur l'ensemble des routes GET parcourues.
