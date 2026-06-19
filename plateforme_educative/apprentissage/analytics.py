import datetime
from django.db.models import Avg, Max, Min, Count, Q
from django.utils import timezone
from accounts.models import Utilisateur, Classe
from apprentissage.models import Cours, Chapitre, Progression, ChapitreVisite, ChapitreComplete
from tuteur_ia.models import SessionQCM

def stats_cours(cours):
    """
    Calcule des statistiques pour un cours donné.
    Retourne un dict prêt pour le template ou JSON.
    """
    # Active ELEVE users who belong to a class of the course's Niveau, OR have a Progression for the course
    students = Utilisateur.objects.filter(role='ELEVE', is_active=True).filter(
        Q(classe__niveau=cours.niveau) | Q(progressions__cours=cours)
    ).distinct()
    nb_inscrits = students.count()
    
    # Taux de complétion moyen
    total_chapitres = cours.chapitres.filter(actif=True).count()
    progressions = Progression.objects.filter(cours=cours).annotate(
        num_valides=Count('chapitres_valides')
    )
    
    if total_chapitres > 0:
        completion_rates = [int((p.num_valides / total_chapitres) * 100) for p in progressions]
        taux_completion_moyen = round(sum(completion_rates) / len(completion_rates), 1) if progressions.exists() else 0.0
    else:
        taux_completion_moyen = 0.0

    # Score QCM moyen
    avg_qcm = SessionQCM.objects.filter(
        chapitre__cours=cours,
        statut__in=['TERMINEE', 'ECHOUEE'],
        score__isnull=False
    ).aggregate(Avg('score'))['score__avg'] or 0.0
    avg_qcm = round(avg_qcm, 1)

    # Nombre de chapitres
    nb_chapitres = total_chapitres

    # Répartition des élèves par tranche de progression
    repartition = {
        '0-25': 0,
        '25-50': 0,
        '50-75': 0,
        '75-100': 0
    }
    if total_chapitres > 0:
        for p in progressions:
            pct = int((p.num_valides / total_chapitres) * 100)
            if pct < 25:
                repartition['0-25'] += 1
            elif pct < 50:
                repartition['25-50'] += 1
            elif pct < 75:
                repartition['50-75'] += 1
            else:
                repartition['75-100'] += 1
        # Students in niveau who don't have a progression record are in the 0-25% bucket
        progressions_student_ids = set(progressions.values_list('etudiant_id', flat=True))
        for student in students:
            if student.id not in progressions_student_ids:
                repartition['0-25'] += 1
    else:
        repartition['0-25'] = nb_inscrits

    return {
        'cours_id': str(cours.id),
        'titre': cours.titre,
        'nb_inscrits': nb_inscrits,
        'taux_completion_moyen': taux_completion_moyen,
        'score_qcm_moyen': avg_qcm,
        'nb_chapitres': nb_chapitres,
        'repartition': repartition
    }

def stats_formateur(formateur):
    """
    Agrège les statistiques des cours créés par un formateur.
    """
    mes_cours = Cours.objects.filter(createur=formateur)
    total_cours = mes_cours.count()
    
    # Unique enrolled students across all formateur's courses
    niveaux_ids = mes_cours.values_list('niveau_id', flat=True).distinct()
    unique_students = Utilisateur.objects.filter(role='ELEVE', is_active=True).filter(
        Q(classe__niveau_id__in=niveaux_ids) | Q(progressions__cours__in=mes_cours)
    ).distinct()
    total_inscrits = unique_students.count()
    
    # Overall average QCM score
    avg_qcm_global = SessionQCM.objects.filter(
        chapitre__cours__in=mes_cours,
        statut__in=['TERMINEE', 'ECHOUEE'],
        score__isnull=False
    ).aggregate(Avg('score'))['score__avg'] or 0.0
    avg_qcm_global = round(avg_qcm_global, 1)
    
    # Per-course detail
    details_cours = []
    for cours in mes_cours:
        details_cours.append(stats_cours(cours))
        
    return {
        'total_cours': total_cours,
        'total_inscrits': total_inscrits,
        'score_qcm_moyen_global': avg_qcm_global,
        'details_cours': details_cours
    }

def stats_eleves_en_difficulte(cours_ou_classe, seuil=50):
    """
    Identifie les élèves dont la progression ou la moyenne QCM est sous le seuil.
    """
    from accounts.models import Classe
    from apprentissage.models import Cours
    
    if isinstance(cours_ou_classe, Cours):
        cours = cours_ou_classe
        students = Utilisateur.objects.filter(role='ELEVE', is_active=True).filter(
            Q(classe__niveau=cours.niveau) | Q(progressions__cours=cours)
        ).distinct()
        
        diff_students = []
        total_chapitres = cours.chapitres.filter(actif=True).count()
        
        for student in students:
            try:
                prog = Progression.objects.get(etudiant=student, cours=cours)
                if total_chapitres > 0:
                    prog_pct = int((prog.chapitres_valides.count() / total_chapitres) * 100)
                else:
                    prog_pct = 0
            except Progression.DoesNotExist:
                prog_pct = 0
                
            avg_qcm = SessionQCM.objects.filter(
                etudiant=student,
                chapitre__cours=cours,
                statut__in=['TERMINEE', 'ECHOUEE'],
                score__isnull=False
            ).aggregate(Avg('score'))['score__avg']
            
            if (avg_qcm is not None and avg_qcm < seuil) or prog_pct < seuil:
                diff_students.append({
                    'etudiant': student,
                    'email': student.email,
                    'progression': prog_pct,
                    'moyenne_qcm': round(avg_qcm, 1) if avg_qcm is not None else None,
                    'cours_titre': cours.titre,
                    'raison': "Progression faible" if prog_pct < seuil else "Moyenne QCM faible"
                })
        return diff_students
        
    elif isinstance(cours_ou_classe, Classe):
        classe = cours_ou_classe
        students = classe.eleves.filter(role='ELEVE', is_active=True)
        
        diff_students = []
        courses = Cours.objects.filter(niveau=classe.niveau, actif=True)
        
        for student in students:
            prog_pcts = []
            for cours in courses:
                total_chapitres = cours.chapitres.filter(actif=True).count()
                try:
                    prog = Progression.objects.get(etudiant=student, cours=cours)
                    if total_chapitres > 0:
                        prog_pcts.append(int((prog.chapitres_valides.count() / total_chapitres) * 100))
                    else:
                        prog_pcts.append(0)
                except Progression.DoesNotExist:
                    prog_pcts.append(0)
                    
            avg_prog = sum(prog_pcts) / len(prog_pcts) if prog_pcts else 0
            
            avg_qcm = SessionQCM.objects.filter(
                etudiant=student,
                chapitre__cours__niveau=classe.niveau,
                statut__in=['TERMINEE', 'ECHOUEE'],
                score__isnull=False
            ).aggregate(Avg('score'))['score__avg']
            
            if avg_prog < seuil or (avg_qcm is not None and avg_qcm < seuil):
                diff_students.append({
                    'etudiant': student,
                    'email': student.email,
                    'progression': round(avg_prog, 1),
                    'moyenne_qcm': round(avg_qcm, 1) if avg_qcm is not None else None,
                    'classe_nom': classe.nom,
                    'raison': "Progression moyenne faible" if avg_prog < seuil else "Moyenne QCM faible"
                })
        return diff_students
    return []

def stats_plateforme():
    """
    Métriques globales de la plateforme pour l'administrateur.
    """
    users_count = Utilisateur.objects.filter(is_active=True).values('role').annotate(count=Count('id'))
    role_counts = {'ELEVE': 0, 'FORMATEUR': 0, 'ADMIN': 0}
    for entry in users_count:
        role_counts[entry['role']] = entry['count']
        
    nb_cours_publies = Cours.objects.filter(actif=True).count()
    nb_sessions_qcm = SessionQCM.objects.filter(statut__in=['TERMINEE', 'ECHOUEE']).count()
    
    total_students = Utilisateur.objects.filter(role='ELEVE', is_active=True).count()
    active_students = Utilisateur.objects.filter(role='ELEVE', is_active=True).filter(
        Q(progressions__isnull=False) | Q(sessions_qcm__isnull=False)
    ).distinct().count()
    
    taux_activite = round((active_students / total_students) * 100, 1) if total_students > 0 else 0.0
    
    return {
        'roles_distribution': role_counts,
        'nb_cours_publies': nb_cours_publies,
        'nb_sessions_qcm': nb_sessions_qcm,
        'taux_activite': taux_activite,
        'total_utilisateurs': Utilisateur.objects.count()
    }
