"""
Vues QCM IA — génération automatique depuis le contenu du PDF.

Flux :
  1. GET  /tuteur/qcm/<chapitre_id>/         → affiche immédiatement la page avec un loader
  2. GET  /tuteur/qcm/<chapitre_id>/generer-api/ → endpoint AJAX qui renvoie le QCM (depuis le cache ou l'IA)
  3. POST /tuteur/qcm/<session_id>/corriger/ → corrige les réponses, calcule le score
  4. GET  /tuteur/qcm/<session_id>/resultats/→ page résultats avec feedback
"""
import json
import logging
import os
import random

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext
from django.views.decorators.http import require_http_methods

from tuteur_ia.models import SessionQCM, QuestionCache
from apprentissage.mixins import ElevePropreDonneeMixin

logger = logging.getLogger(__name__)

LETTRES = ['A', 'B', 'C', 'D']


# ── Génération du QCM par IA ──────────────────────────────────────────────────

# Limite de contexte envoyé au LLM pour la génération QCM.
# Un prompt trop long ralentit massivement la génération (tokens ∝ temps).
# 3 000 chars ≈ 750 tokens — suffisant pour 8 questions pédagogiques et ~10 s
# de prefill de moins qu'à 4 000 sur CPU.
_QCM_MAX_CONTENT_CHARS = 3_000


def _get_pdf_content_for_qcm(chapitre) -> str:
    """
    Récupère le contenu du PDF indexé pour ce chapitre depuis ChromaDB.
    Retourne au maximum _QCM_MAX_CONTENT_CHARS caractères (premiers chunks)
    pour garder le prompt LLM court et la génération rapide.
    """
    from tuteur_ia.tools.chroma_store import get_collection
    try:
        collection = get_collection()
        try:
            res = collection.get(
                where={"chapitre_id": str(chapitre.id)},
                include=["documents", "metadatas"]
            )
        except Exception as err:
            logger.warning(f"[ChromaDB QCM Fallback] collection.get avec filtre where a échoué ({err}), bascule sur filtrage Python.")
            raw = collection.get(include=["documents", "metadatas"])
            docs, metas = [], []
            if raw and raw.get("documents"):
                for doc, meta in zip(raw["documents"], raw["metadatas"]):
                    if meta and str(meta.get("chapitre_id")) == str(chapitre.id):
                        docs.append(doc)
                        metas.append(meta)
            res = {"documents": docs, "metadatas": metas}

        docs = res.get("documents", [])
        metas = res.get("metadatas", [])

        if docs:
            # Tri par index de chunk pour respecter l'ordre d'origine
            indexed_docs = []
            for doc, meta in zip(docs, metas):
                try:
                    idx = int(meta.get("chunk_index", 0))
                except (ValueError, TypeError):
                    idx = 0
                indexed_docs.append((idx, doc))

            indexed_docs.sort(key=lambda x: x[0])
            sorted_docs = [doc for _, doc in indexed_docs]

            # Concaténer les chunks et tronquer à la limite
            full_content = "\n\n---\n\n".join(sorted_docs)
            if len(full_content) > _QCM_MAX_CONTENT_CHARS:
                full_content = full_content[:_QCM_MAX_CONTENT_CHARS]
                logger.info(
                    f"QCM content tronqué à {_QCM_MAX_CONTENT_CHARS} chars "
                    f"({len(sorted_docs)} chunks disponibles)"
                )
            else:
                logger.info(f"QCM content chargé depuis ChromaDB : {len(sorted_docs)} chunks")
            return full_content
    except Exception as e:
        logger.error(f"Erreur extraction directe ChromaDB : {e}", exc_info=True)

    return ""


def _normaliser_question(q: dict) -> dict | None:
    """
    Nettoie une question produite par le LLM avant validation.

    Les petits modèles locaux (qwen2.5-1.5b) respectent mal un schéma strict :
    nombre d'options variable (3 au lieu de 4), `reponse_correcte` parfois
    renvoyée sous forme de liste, clé `explanation` au lieu de `explication`…
    On récupère ce qui est exploitable au lieu de tout rejeter.

    Retourne un dict propre {question, options, reponse_correcte, explication}
    ou None si la question est irrécupérable.
    """
    if not isinstance(q, dict):
        return None

    question = str(q.get('question') or '').strip()

    options = q.get('options')
    if not isinstance(options, list):
        return None
    options = [str(o).strip() for o in options if str(o).strip()]
    options = list(dict.fromkeys(options))  # dédoublonne en gardant l'ordre

    reponse = q.get('reponse_correcte')
    if isinstance(reponse, list):
        reponse = reponse[0] if reponse else ''
    reponse = str(reponse or '').strip()

    explication = str(q.get('explication') or q.get('explanation') or '').strip()

    # Une question a besoin d'un énoncé, d'une bonne réponse et d'au moins
    # 3 choix pour rester un vrai QCM.
    if not question or not reponse or len(options) < 3:
        return None

    # La bonne réponse doit figurer parmi les options (sinon l'élève ne peut
    # jamais cocher juste). Tolérance sur la ponctuation / la casse.
    if reponse not in options:
        _norm = lambda s: s.rstrip(' .').casefold()
        match = next((o for o in options if _norm(o) == _norm(reponse)), None)
        if match:
            reponse = match
        elif len(options) < 4:
            options.append(reponse)
        else:
            options[-1] = reponse

    # Le template n'affiche que 4 lettres (A/B/C/D) : plafonner à 4 options
    # en conservant toujours la bonne réponse.
    if len(options) > 4:
        autres = [o for o in options if o != reponse][:3]
        options = [reponse, *autres]

    # Le petit modèle local ne donne parfois que 3 options : compléter à 4
    # avec un distracteur neutre (toujours faux ici) pour un QCM homogène.
    if len(options) == 3:
        blob = " ".join(options + [question]).lower()
        _fr = any(c in blob for c in "àâäéèêëïîïôûùüç") or any(
            f" {w} " in f" {blob} " for w in ("le", "la", "les", "un", "une", "des", "est", "quoi")
        )
        options.append("Aucune de ces réponses" if _fr else "None of the above")

    # Mélanger pour que la bonne réponse ne soit pas toujours au même rang.
    random.shuffle(options)

    if not explication:
        explication = gettext("Voir le contenu du chapitre pour la justification.")

    return {
        'question': question,
        'options': options,
        'reponse_correcte': reponse,
        'explication': explication,
    }


def _extraire_questions_llm(content: str) -> list[dict]:
    """
    Extrait toutes les questions d'une réponse LLM, même mal formée.

    Les petits modèles locaux (qwen2.5-1.5b) produisent souvent :
      - la clé "questions" répétée : {"questions":[A],"questions":[B]}
        (json.loads n'en garde qu'une) ;
      - des objets JSON concaténés sans tableau : {...}{...} ;
      - un JSON tronqué en fin de génération.
    On récupère un maximum de dicts {question, options, …}.
    """
    if not content:
        return []

    out: list[dict] = []

    def _absorber(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get('questions'), list):
                out.extend(x for x in obj['questions'] if isinstance(x, dict))
            elif 'question' in obj or 'options' in obj:
                out.append(obj)
        elif isinstance(obj, list):
            out.extend(x for x in obj if isinstance(x, dict))

    # Fusionne les clés "questions" dupliquées à l'intérieur d'un même objet.
    def _pairs_hook(pairs):
        d = {}
        for k, v in pairs:
            if k == 'questions' and isinstance(v, list):
                d.setdefault('questions', []).extend(v)
            elif k not in d:
                d[k] = v
        return d

    dec = json.JSONDecoder(object_pairs_hook=_pairs_hook)

    # Scanne tous les objets JSON de premier niveau de la sortie.
    i, n = 0, len(content)
    while i < n:
        j = content.find('{', i)
        if j == -1:
            break
        try:
            obj, end = dec.raw_decode(content, j)
            _absorber(obj)
            i = max(end, j + 1)
        except json.JSONDecodeError:
            i = j + 1

    # Filet de sécurité : rien extrait → tenter une réparation de troncature.
    if not out:
        s, e = content.find('{'), content.rfind('}')
        if s != -1 and e > s:
            frag = content[s:e + 1]
            for suffixe in ('', ']}', '"}]}', '"}]} '):
                try:
                    _absorber(json.loads(frag + suffixe, object_pairs_hook=_pairs_hook))
                except json.JSONDecodeError:
                    continue
                if out:
                    break

    # Dédoublonnage par énoncé.
    vus, uniq = set(), []
    for q in out:
        cle = str(q.get('question', '')).strip().casefold()
        if cle and cle not in vus:
            vus.add(cle)
            uniq.append(q)
    return uniq


def _generer_questions_ia(chapitre, n_questions: int = 8) -> tuple[list[dict], str]:
    """
    Génère n questions QCM depuis le contenu ChromaDB du chapitre.

    Le modèle hors-ligne (qwen2.5-1.5b) est petit et instable : on appelle
    le LLM jusqu'à 3 fois et on accumule les questions valides d'un appel à
    l'autre jusqu'à en avoir assez.
    """
    from tuteur_ia.agents.llm_factory import get_llm, with_language, is_llm_unavailable_error
    from langchain_core.messages import SystemMessage, HumanMessage

    # Récupérer le contenu réel du PDF (tronqué à _QCM_MAX_CONTENT_CHARS)
    contenu = _get_pdf_content_for_qcm(chapitre)

    if not contenu or contenu.startswith('['):
        logger.warning(f"Contenu PDF vide ou non indexé pour le chapitre {chapitre.id}")
        return [], 'no_content'

    # max_tokens explicite : 8 questions JSON ≈ 900 tokens ; 1200 laisse une
    # marge sans permettre au petit modèle de partir en boucle (coûteux sur CPU).
    llm = get_llm(temperature=0.4, max_tokens=1200)

    system_prompt = (
        f"Tu crées {n_questions} questions QCM en JSON, basées STRICTEMENT sur le "
        "texte fourni. Réponds UNIQUEMENT avec UN SEUL objet JSON, sans aucun texte "
        "autour. La clé \"questions\" apparaît UNE SEULE FOIS et contient un tableau. "
        "Chaque question DOIT avoir EXACTEMENT 4 options courtes (max 6 mots), une "
        "seule bonne réponse copiée mot pour mot depuis les options, et une "
        "explication courte. "
        'Format EXACT : {"questions":[{"question":"...","options":["...","...","...","..."],'
        '"reponse_correcte":"...","explication":"..."}]}'
    )
    user_prompt = (
        f"TEXTE SOURCE :\n{contenu}\n\n"
        f"Génère {n_questions} questions QCM tirées de ce texte. "
        "Un seul tableau \"questions\", 4 options par question."
    )
    messages = [
        SystemMessage(content=with_language(system_prompt)),
        HumanMessage(content=user_prompt),
    ]

    # Plancher : en dessous de 3 questions valides on renvoie une erreur ;
    # sinon on sert ce qu'on a (le cache s'enrichit d'un appel à l'autre).
    cible = 3
    valid: list[dict] = []
    vus: set[str] = set()

    # Plafond global : on ne relance pas d'appel LLM au-delà de cette durée,
    # pour ne pas laisser une requête HTTP (ou un warmup) traîner plusieurs
    # minutes si le moteur local est lent. On sert ce qu'on a accumulé.
    import time as _time
    deadline = _time.monotonic() + float(os.environ.get("QCM_GEN_MAX_SECONDS", "110"))

    try:
        for tentative in range(3):
            if tentative > 0 and _time.monotonic() > deadline:
                logger.warning("[QCM IA] plafond de temps atteint — arrêt des tentatives.")
                break
            logger.info(
                f"[QCM IA] Appel LLM {tentative + 1}/3 pour '{chapitre.titre}' "
                f"({len(contenu)} chars de contexte, {n_questions} questions)"
            )
            response = llm.invoke(messages)
            brutes = _extraire_questions_llm((response.content or '').strip())
            for q in brutes:
                nq = _normaliser_question(q)
                if not nq:
                    continue
                cle = nq['question'].casefold()
                if cle in vus:
                    continue
                vus.add(cle)
                valid.append(nq)
            _f = {"Aucune de ces réponses", "None of the above"}
            complets = sum(1 for q in valid if not any(o in _f for o in q['options']))
            logger.info(
                f"[QCM IA] tentative {tentative + 1} : {len(brutes)} brutes -> "
                f"{len(valid)} valides cumulées ({complets} à 4 options fournies)."
            )
            if complets >= n_questions:
                break

        if len(valid) >= cible:
            # Privilégier les questions dont le modèle a fourni lui-même les
            # 4 options ; celles complétées par un distracteur neutre passent
            # après (elles ne servent que s'il n'y en a pas assez de « vraies »).
            _fillers = {"Aucune de ces réponses", "None of the above"}
            random.shuffle(valid)
            valid.sort(key=lambda q: any(o in _fillers for o in q['options']))
            retenues = valid[:n_questions]
            random.shuffle(retenues)
            return retenues, ''
        logger.warning(
            f"[QCM IA] échec : {len(valid)} questions valides seulement "
            f"(cible {cible}) après 3 tentatives."
        )
    except Exception as e:
        logger.error(f"Erreur génération QCM IA : {e}", exc_info=True)
        if is_llm_unavailable_error(e):
            return [], 'llm_unavailable'

    return [], 'generation_failed'


def _ajouter_lettres(questions: list[dict]) -> list[dict]:
    """
    Ajoute les lettres A/B/C/D à chaque option pour le template.
    """
    result = []
    for q in questions:
        q_copy = dict(q)
        q_copy['options_avec_lettres'] = [
            {'lettre': LETTRES[i], 'texte': opt}
            for i, opt in enumerate(q.get('options', [])[:4])
        ]
        result.append(q_copy)
    return result


# ── Vues ──────────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def demarrer_qcm(request, chapitre_id):
    """
    GET → Affiche immédiatement la page avec le loader HTML.
    La génération effective se fera de manière asynchrone via AJAX.
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)
    tentative = SessionQCM.objects.filter(etudiant=request.user, chapitre=chapitre).count() + 1
    
    # QCM fixe de 8 questions
    n_questions = 8

    return render(request, 'tuteur_ia/qcm.html', {
        'chapitre':    chapitre,
        'cours':       chapitre.cours,
        'n_questions': n_questions,
        'tentative':   tentative,
        'session':     None,
        'questions':   [],
    })


@login_required
@require_http_methods(['GET'])
def generer_qcm_api(request, chapitre_id):
    """
    GET → Endpoint API appelé par AJAX.
    Récupère les questions depuis le cache ou appelle l'IA, crée la SessionQCM et renvoie le JSON.
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)
    tentative = SessionQCM.objects.filter(etudiant=request.user, chapitre=chapitre).count() + 1
    
    # Toujours 8 questions
    n_questions = 8

    # Récupération / Création du cache
    cache, created = QuestionCache.objects.get_or_create(chapitre=chapitre)
    questions_pool = cache.questions or []

    # Vérifier si on a assez de questions en cache
    if len(questions_pool) >= n_questions:
        # Piocher aléatoirement dans la banque de questions existantes
        questions = random.sample(questions_pool, n_questions)
        logger.info(f"QCM chargé depuis le cache pour le chapitre {chapitre_id} (pool: {len(questions_pool)})")
    else:
        # Appeler le LLM pour générer de nouvelles questions
        questions, reason = _generer_questions_ia(chapitre, n_questions=n_questions)
        if not questions:
            if reason == 'no_content':
                return JsonResponse({
                    'error': gettext('Aucun document PDF indexé pour ce chapitre.'),
                    'detail': gettext("Le formateur doit d'abord uploader un PDF dans ce chapitre pour que le QCM puisse être généré automatiquement."),
                    'no_pdf': True,
                }, status=404)
            elif reason == 'llm_unavailable' and not questions_pool:
                return JsonResponse({
                    'error': gettext("Le service IA n'est pas disponible pour le moment."),
                    'detail': gettext("La génération de QCM nécessite le moteur IA (local ou en ligne). Réessayez plus tard ou prévenez votre formateur."),
                    'llm_unavailable': True,
                }, status=503)
            elif questions_pool:
                logger.warning(f"La génération a échoué mais {len(questions_pool)} questions existent en cache. Utilisation du cache partiel.")
                # Utiliser les questions du cache même si on n'en a pas assez
                questions = questions_pool
            else:
                return JsonResponse({
                    'error': gettext("La génération du QCM par l'IA a échoué. Réessayez dans quelques instants."),
                    'detail': gettext("Le contenu du chapitre est bien indexé, mais l'IA n'a pas réussi à produire les questions cette fois-ci."),
                    'no_pdf': False,
                }, status=500)

        # Enricheur de cache : Ajouter les nouvelles questions sans doublons
        existing_texts = {q['question'].strip().lower() for q in questions_pool}
        added = 0
        for q in questions:
            if q['question'].strip().lower() not in existing_texts:
                questions_pool.append(q)
                added += 1
        
        if added > 0:
            cache.questions = questions_pool
            cache.save()
            logger.info(f"Cache enrichi de {added} nouvelles questions pour le chapitre {chapitre_id}")

    # Création de la session QCM uniquement lorsque les questions sont prêtes
    session = SessionQCM.objects.create(
        etudiant=request.user,
        chapitre=chapitre,
        questions=questions,
        tentative=tentative,
    )

    questions_template = _ajouter_lettres(questions)

    return JsonResponse({
        'session_id':           str(session.id),
        'questions':            questions_template,
        'n_questions':          len(questions),
        'tentative':            tentative,
    })


@login_required
@ElevePropreDonneeMixin.as_decorator()
@require_http_methods(['POST'])
def corriger_qcm(request, session_id):
    """
    Reçoit les réponses, calcule le score, retourne JSON.
    """
    session = get_object_or_404(SessionQCM, id=session_id)

    try:
        data     = json.loads(request.body)
        reponses = data.get('reponses', {})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)

    questions = session.questions
    total     = len(questions)
    correctes = 0
    details   = []

    for i, question in enumerate(questions):
        reponse_choisie = reponses.get(str(i), '')
        bonne_reponse   = question['reponse_correcte']
        est_correcte    = reponse_choisie.strip() == bonne_reponse.strip()

        if est_correcte:
            correctes += 1

        details.append({
            'question':        question['question'],
            'reponse_choisie': reponse_choisie,
            'bonne_reponse':   bonne_reponse,
            'est_correcte':    est_correcte,
            'explication':     question.get('explication', ''),
            'options':         question.get('options', []),
        })

    score  = round((correctes / total) * 100) if total > 0 else 0
    statut = 'TERMINEE' if score >= 80 else 'ECHOUEE'

    session.reponses = reponses
    session.score    = score
    session.statut   = statut
    session.save()

    try:
        from accounts.notifications import notifier
        from django.urls import reverse
        notifier(
            destinataire=session.etudiant,
            type='QCM_CORRIGE',
            titre=gettext("QCM Corrigé : %(chapitre)s") % {'chapitre': session.chapitre.titre},
            message=gettext("Tu as complété le QCM du chapitre '%(chapitre)s' avec un score de %(score)s/100.") % {'chapitre': session.chapitre.titre, 'score': score},
            url=reverse('tuteur_ia:resultats_qcm', args=[session.id])
        )
    except Exception as notif_err:
        logger.error(f"Erreur d'envoi de notification de correction QCM : {notif_err}", exc_info=True)

    if score >= 80:
        feedback = {
            'type':    'success',
            'titre':   gettext('🎉 Bravo ! Tu as obtenu %(score)s/100 !') % {'score': score},
            'message': gettext('Excellent travail ! Tu maîtrises bien ce chapitre. Tu peux passer au chapitre suivant.'),
            'action':  'next_chapter',
        }
        try:
            from apprentissage.models import Progression, ChapitreComplete
            progression, _ = Progression.objects.get_or_create(
                etudiant=request.user,
                cours=session.chapitre.cours
            )
            progression.chapitres_valides.add(session.chapitre)
            ChapitreComplete.objects.update_or_create(
                etudiant=request.user,
                chapitre=session.chapitre,
            )
        except Exception as e:
            logger.error(f"Erreur lors de la validation automatique du chapitre : {e}", exc_info=True)
    else:
        feedback = {
            'type':    'retry',
            'titre':   gettext('Score : %(score)s/100') % {'score': score},
            'message': gettext('Tu as eu %(correctes)s bonne(s) réponse(s) sur %(total)s. Relis le chapitre et réessaie !') % {'correctes': correctes, 'total': total},
            'action':  'retry',
        }

    prochain_chapitre_id = None
    try:
        chapitres    = list(session.chapitre.cours.chapitres.filter(actif=True).order_by('ordre').values('id', 'ordre'))
        ordre_actuel = session.chapitre.ordre
        for c in chapitres:
            if c['ordre'] > ordre_actuel:
                prochain_chapitre_id = str(c['id'])
                break
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la récupération du prochain chapitre: {e}")

    return JsonResponse({
        'score':                score,
        'correctes':            correctes,
        'total':                total,
        'statut':               statut,
        'feedback':             feedback,
        'details':              details,
        'prochain_chapitre_id': prochain_chapitre_id,
        'session_id':           str(session.id),
    })


@login_required
@ElevePropreDonneeMixin.as_decorator()
def resultats_qcm(request, session_id):
    """Page de résultats détaillés du QCM."""
    session  = get_object_or_404(SessionQCM, id=session_id)
    chapitre = session.chapitre

    details = []
    for i, question in enumerate(session.questions):
        reponse_choisie = session.reponses.get(str(i), '')
        bonne_reponse   = question['reponse_correcte']
        details.append({
            'numero':          i + 1,
            'question':        question['question'],
            'options':         question.get('options', []),
            'reponse_choisie': reponse_choisie,
            'bonne_reponse':   bonne_reponse,
            'est_correcte':    reponse_choisie.strip() == bonne_reponse.strip(),
            'explication':     question.get('explication', ''),
        })

    prochain_chapitre = None
    try:
        prochain_chapitre = (
            chapitre.cours.chapitres
            .filter(actif=True, ordre__gt=chapitre.ordre)
            .order_by('ordre')
            .first()
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la récupération du prochain chapitre dans resultats_qcm: {e}")

    return render(request, 'tuteur_ia/qcm_resultats.html', {
        'session':           session,
        'chapitre':          chapitre,
        'cours':             chapitre.cours,
        'details':           details,
        'score':             session.score,
        'prochain_chapitre': prochain_chapitre,
        'peut_avancer':      (session.score or 0) >= 80,
    })


@login_required
@require_http_methods(['GET'])
def verifier_statut_qcm(request, task_id):
    """
    Endpoint de polling pour connaître l'état d'une tâche Celery de génération QCM.
    Retourne :
      - {"status": "en_cours"} si la tâche est en attente ou en cours
      - {"status": "pret", "session_id": ..., "questions": ...} si terminée
      - {"status": "erreur", "detail": ...} en cas d'échec
    """
    # Un id de tâche Celery est un UUID : sinon inutile d'interroger le backend
    # (qui renvoie PENDING pour n'importe quoi et ferait boucler le client).
    import uuid
    try:
        uuid.UUID(str(task_id))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'erreur', 'detail': gettext("Tâche introuvable.")}, status=404)

    try:
        from celery.result import AsyncResult
        result = AsyncResult(task_id)

        if result.state == 'PENDING' or result.state == 'STARTED':
            return JsonResponse({'status': 'en_cours'})

        if result.state == 'SUCCESS':
            data = result.get()
            if data and 'error' in data:
                return JsonResponse({'status': 'erreur', 'detail': data['error']}, status=404)
            return JsonResponse({'status': 'pret', **data})

        if result.state == 'FAILURE':
            return JsonResponse({
                'status': 'erreur',
                'detail': str(result.result),
            }, status=500)

        return JsonResponse({'status': 'en_cours'})

    except Exception as e:
        logger.error(f"Erreur vérification statut QCM task {task_id}: {e}", exc_info=True)
        return JsonResponse({'status': 'erreur', 'detail': gettext("Erreur lors de la vérification du statut.")}, status=500)

