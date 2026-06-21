"""
Logique d'agrégation des notes pour le carnet de notes.
Fournit la fonction calculer_bulletin(etudiant) qui agrège :
  - Les meilleurs scores QCM par chapitre (depuis tuteur_ia.SessionQCM)
  - La progression de l'étudiant dans chaque cours (depuis apprentissage.Progression)
  - Une moyenne par cours et une moyenne générale
"""
from django.db.models import Max


def calculer_bulletin(etudiant):
    """
    Agrège les évaluations d'un étudiant et retourne un bulletin structuré.

    Returns:
        dict avec :
          - 'cours'        : liste des cours de l'étudiant
          - 'moyenne_generale' : float ou None
          - chaque entrée cours contient :
              * 'cours'           : objet Cours
              * 'progression'     : pourcentage de progression (0-100)
              * 'chapitres'       : liste de dict par chapitre avec meilleur score
              * 'moyenne_cours'   : moyenne des meilleurs scores du cours (ou None)
              * 'nb_tentes'       : nb chapitres pour lesquels un QCM a été tenté
    """
    from apprentissage.models import Cours, Chapitre, Progression, ChapitreVisite
    from tuteur_ia.models import SessionQCM, SessionTuteur

    # 1. Récupérer tous les cours associés à cet étudiant (par niveau, progression ou activités)
    cours_set = set()
    
    # Progressions
    progressions = Progression.objects.filter(etudiant=etudiant).select_related('cours')
    progressions_map = {prog.cours.id: prog for prog in progressions}
    for cours_id in progressions_map.keys():
        cours_set.add(progressions_map[cours_id].cours)
        
    # Classe / Niveau
    classe = getattr(etudiant, 'classe', None)
    niveau = getattr(classe, 'niveau', None)
    if niveau:
        for c in Cours.objects.filter(niveau=niveau, actif=True):
            cours_set.add(c)
            
    # Activités (Visites de chapitres)
    for visit in ChapitreVisite.objects.filter(etudiant=etudiant).select_related('chapitre__cours'):
        cours_set.add(visit.chapitre.cours)
        
    # Activités (Sessions QCM)
    for qcm in SessionQCM.objects.filter(etudiant=etudiant).select_related('chapitre__cours'):
        cours_set.add(qcm.chapitre.cours)
        
    # Activités (Sessions Study Buddy)
    for tut in SessionTuteur.objects.filter(etudiant=etudiant).select_related('chapitre__cours'):
        cours_set.add(tut.chapitre.cours)

    # 2. Récupérer les meilleurs scores QCM par chapitre pour cet étudiant
    meilleurs_scores = (
        SessionQCM.objects
        .filter(etudiant=etudiant, statut__in=['TERMINEE', 'ECHOUEE'])
        .values('chapitre_id')
        .annotate(meilleur_score=Max('score'))
    )
    scores_par_chapitre = {
        str(entry['chapitre_id']): entry['meilleur_score']
        for entry in meilleurs_scores
    }

    bulletin_cours = []
    toutes_moyennes = []

    # Trier la liste des cours par titre
    sorted_cours = sorted(list(cours_set), key=lambda x: x.titre)

    for cours in sorted_cours:
        chapitres = list(
            cours.chapitres.filter(actif=True).order_by('ordre')
        )

        chapitres_data = []
        scores_du_cours = []

        for chapitre in chapitres:
            cid = str(chapitre.id)
            score = scores_par_chapitre.get(cid)

            if score is not None:
                statut = 'REUSSI' if score >= 80 else 'ECHOUE'
                scores_du_cours.append(score)
            else:
                statut = 'NON_TENTE'

            chapitres_data.append({
                'chapitre': chapitre,
                'meilleur_score': score,
                'statut': statut,
            })

        nb_tentes = len(scores_du_cours)
        moyenne_cours = (sum(scores_du_cours) / nb_tentes) if nb_tentes > 0 else None

        if moyenne_cours is not None:
            toutes_moyennes.append(moyenne_cours)

        # Progression
        progression = progressions_map.get(cours.id)
        prog_pourcentage = progression.pourcentage if progression else 0

        bulletin_cours.append({
            'cours': cours,
            'progression': prog_pourcentage,
            'chapitres': chapitres_data,
            'moyenne_cours': round(moyenne_cours, 1) if moyenne_cours is not None else None,
            'nb_tentes': nb_tentes,
        })

    moyenne_generale = (
        round(sum(toutes_moyennes) / len(toutes_moyennes), 1)
        if toutes_moyennes else None
    )

    return {
        'cours': bulletin_cours,
        'moyenne_generale': moyenne_generale,
    }
