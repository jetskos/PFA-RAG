import datetime
from django.db.models import Avg, Max, Min, Count, Q
from accounts.models import Classe, Utilisateur
from apprentissage.models import Cours, Progression, ChapitreComplete
from tuteur_ia.models import SessionQCM

def taux_completion_par_classe(cours_id):
    """
    Calcule le taux moyen de complétion du cours pour chaque classe du niveau.
    Retourne un dict {classe_objet: {'pourcentage': int, 'nb_eleves': int}}
    """
    try:
        cours = Cours.objects.get(id=cours_id)
    except Cours.DoesNotExist:
        return {}

    classes = Classe.objects.filter(niveau=cours.niveau, actif=True)
    result = {}

    for classe in classes:
        eleves = classe.eleves.filter(role='ELEVE', is_active=True)
        nb_eleves = eleves.count()
        if nb_eleves == 0:
            result[classe] = {'pourcentage': 0, 'nb_eleves': 0}
            continue

        total_pct = 0
        progressions = {
            p.etudiant_id: p.pourcentage
            for p in Progression.objects.filter(cours=cours, etudiant__in=eleves)
        }
        for eleve in eleves:
            total_pct += progressions.get(eleve.id, 0)

        avg_pct = round(total_pct / nb_eleves)
        result[classe] = {'pourcentage': avg_pct, 'nb_eleves': nb_eleves}

    return result

def eleves_en_difficulte(cours_id, seuil=50):
    """
    Identifie les élèves dont la moyenne aux QCM de ce cours est inférieure au seuil.
    Retourne un QuerySet d'étudiants annoté avec le nombre de devoirs rendus.
    De plus, attache dynamiquement à chaque objet étudiant :
      - moyenne_qcm : float
      - taux_completion : int
    """
    try:
        cours = Cours.objects.get(id=cours_id)
    except Cours.DoesNotExist:
        return Utilisateur.objects.none()

    students = Utilisateur.objects.filter(
        role='ELEVE',
        is_active=True,
        classe__niveau=cours.niveau
    ).annotate(
        nb_devoirs_rendus=Count(
            'soumissions',
            filter=Q(soumissions__devoir__chapitre__cours_id=cours_id)
        )
    )

    # 1. Calculer le meilleur score par étudiant et par chapitre
    max_scores = SessionQCM.objects.filter(
        chapitre__cours_id=cours_id,
        statut__in=['TERMINEE', 'ECHOUEE']
    ).values('etudiant_id', 'chapitre_id').annotate(max_score=Max('score'))

    # Groupement par étudiant
    student_scores = {}
    for entry in max_scores:
        uid = entry['etudiant_id']
        score = entry['max_score']
        if uid not in student_scores:
            student_scores[uid] = []
        student_scores[uid].append(score)

    qcm_averages = {}
    for uid, scores in student_scores.items():
        qcm_averages[uid] = sum(scores) / len(scores) if scores else 0

    # 2. Filtrer les élèves en difficulté
    in_difficulty_ids = []
    for student in students:
        avg_qcm = qcm_averages.get(student.id, 0)
        if avg_qcm < seuil:
            in_difficulty_ids.append(student.id)

    queryset = students.filter(id__in=in_difficulty_ids)

    # 3. Attacher les données supplémentaires
    for student in queryset:
        student.moyenne_qcm = round(qcm_averages.get(student.id, 0), 1)
        try:
            prog = Progression.objects.get(etudiant=student, cours=cours)
            student.taux_completion = prog.pourcentage
        except Progression.DoesNotExist:
            student.taux_completion = 0

    return queryset

def temps_passe_par_eleve(cours_id):
    """
    Calcule le temps approximé passé par chaque élève sur le cours.
    Retourne un dict {str(student_id): timedelta}

    Limites méthodologiques importantes :
    1. Ce calcul représente le delta de temps écoulé entre le premier et le dernier événement
       de complétion de chapitre enregistré pour ce cours.
    2. Il ne s'agit pas du temps de connexion actif réel. Par exemple, si un étudiant valide
       le chapitre 1 le lundi à 10h et le chapitre 2 le mardi à 10h, l'estimation sera de 24 heures,
       même s'il n'a passé que 30 minutes de travail actif.
    3. Si l'élève n'a validé qu'un seul chapitre (ou aucun), le delta est égal à 0.
    """
    completions = ChapitreComplete.objects.filter(
        chapitre__cours_id=cours_id
    ).values('etudiant_id').annotate(
        premier=Min('date_completion'),
        dernier=Max('date_completion')
    )

    result = {}
    for entry in completions:
        uid = str(entry['etudiant_id'])
        premier = entry['premier']
        dernier = entry['dernier']
        if premier and dernier:
            result[uid] = dernier - premier
        else:
            result[uid] = datetime.timedelta(0)

    return result
