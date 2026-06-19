import csv
import datetime
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from accounts.models import Utilisateur, Classe
from apprentissage.models import Cours, Progression
from .calculer_analytics import (
    taux_completion_par_classe,
    eleves_en_difficulte,
    temps_passe_par_eleve
)

from apprentissage.mixins import FormateurCoursRequiredMixin

@login_required
@FormateurCoursRequiredMixin.as_decorator(allow_admin=True)
def formateur_course_analytics(request, cours_id):
    """
    Dashboard d'analytics pour un cours spécifique destiné au formateur.
    """
    cours = get_object_or_404(Cours, id=cours_id)

    seuil = int(request.GET.get('seuil', 50))
    classe_id = request.GET.get('classe')

    # 1. Taux de complétion par classe
    completion_data = taux_completion_par_classe(cours.id)
    
    # Filtrer par classe si demandé
    if classe_id:
        completion_data = {
            k: v for k, v in completion_data.items()
            if str(k.id) == classe_id
        }

    # 2. Élèves en difficulté
    etudiants_diff = eleves_en_difficulte(cours.id, seuil=seuil)
    if classe_id:
        etudiants_diff = etudiants_diff.filter(classe_id=classe_id)

    # 3. Temps passé par élève
    temps_data = temps_passe_par_eleve(cours.id)
    
    # Associer les informations de temps passé à chaque étudiant en difficulté
    # et construire la liste complète des élèves pour la section d'estimation de temps
    eleves_cours = Utilisateur.objects.filter(
        role='ELEVE',
        is_active=True,
        classe__niveau=cours.niveau
    ).select_related('classe')
    
    if classe_id:
        eleves_cours = eleves_cours.filter(classe_id=classe_id)

    list_temps_passe = []
    for student in eleves_cours:
        delta = temps_data.get(str(student.id), datetime.timedelta(0))
        # Formater le delta de manière lisible (jours, heures, minutes)
        total_seconds = int(delta.total_seconds())
        jours = total_seconds // 86400
        heures = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        temps_str = ""
        if jours > 0:
            temps_str += f"{jours}j "
        if heures > 0 or jours > 0:
            temps_str += f"{heures}h "
        temps_str += f"{minutes}m"

        # Taux de complétion individuel
        try:
            prog = Progression.objects.get(etudiant=student, cours=cours)
            completion = prog.pourcentage
        except Progression.DoesNotExist:
            completion = 0

        list_temps_passe.append({
            'student': student,
            'temps_str': temps_str,
            'completion': completion,
            'delta': delta,
        })

    # Trier par temps passé décroissant
    list_temps_passe.sort(key=lambda x: x['delta'], reverse=True)

    # Liste des classes pour le filtre
    classes = Classe.objects.filter(niveau=cours.niveau, actif=True)

    return render(request, 'analytics/formateur_analytics.html', {
        'cours': cours,
        'completion_data': completion_data,
        'etudiants_diff': etudiants_diff,
        'list_temps_passe': list_temps_passe,
        'classes': classes,
        'seuil': seuil,
        'classe_selectionnee': classe_id,
        'titre_page': f"Statistiques — {cours.titre}",
    })

@login_required
def admin_dashboard_analytics(request):
    """
    Dashboard d'analytics global pour les administrateurs.
    """
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return HttpResponseForbidden("Accès réservé aux administrateurs.")

    courses = Cours.objects.filter(actif=True).select_related('niveau', 'createur')
    classes = Classe.objects.filter(actif=True).select_related('niveau')

    # Classement des cours par taux d'échec
    classement_cours = []
    for cours in courses:
        # Total élèves dans le niveau
        eleves = Utilisateur.objects.filter(
            role='ELEVE',
            is_active=True,
            classe__niveau=cours.niveau
        )
        total_eleves = eleves.count()
        if total_eleves == 0:
            classement_cours.append({
                'cours': cours,
                'taux_echec': 0,
                'nb_diff': 0,
                'total_eleves': 0,
            })
            continue

        # Élèves en difficulté (seuil par défaut de 50)
        nb_diff = eleves_en_difficulte(cours.id, seuil=50).count()
        taux_echec = round((nb_diff / total_eleves) * 100)
        
        classement_cours.append({
            'cours': cours,
            'taux_echec': taux_echec,
            'nb_diff': nb_diff,
            'total_eleves': total_eleves,
        })

    # Trier par taux d'échec décroissant
    classement_cours.sort(key=lambda x: x['taux_echec'], reverse=True)

    return render(request, 'analytics/admin_analytics.html', {
        'classement_cours': classement_cours,
        'total_cours': courses.count(),
        'total_classes': classes.count(),
        'titre_page': "Tableau de Bord Analytics Global",
    })

@login_required
@FormateurCoursRequiredMixin.as_decorator(allow_admin=True)
def export_formateur_analytics_csv(request, cours_id):
    """
    Exporte les statistiques d'un cours en format CSV.
    """
    cours = get_object_or_404(Cours, id=cours_id)

    classe_id = request.GET.get('classe')
    seuil = int(request.GET.get('seuil', 50))

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="analytics_{cours.titre.replace(" ", "_")}.csv"'
    response.write('\ufeff') # BOM Excel

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Etudiant', 'Classe', 'Moyenne QCM (/100)', 'Taux de completion (%)', 'Devoirs rendus'])

    etudiants_diff = eleves_en_difficulte(cours.id, seuil=seuil)
    if classe_id:
        etudiants_diff = etudiants_diff.filter(classe_id=classe_id)

    for student in etudiants_diff:
        writer.writerow([
            student.get_full_name(),
            student.classe.nom if student.classe else 'Sans classe',
            getattr(student, 'moyenne_qcm', 0),
            getattr(student, 'taux_completion', 0),
            student.nb_devoirs_rendus
        ])

    return response

@login_required
def export_admin_analytics_csv(request):
    """
    Exporte le classement des cours par taux d'échec global en CSV.
    """
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return HttpResponseForbidden("Accès réservé aux administrateurs.")

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="classement_cours_echec.csv"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Cours', 'Niveau', 'Formateur', 'Nombre d\'eleves en difficulte', 'Nombre total d\'eleves', 'Taux d\'echec (%)'])

    courses = Cours.objects.filter(actif=True).select_related('niveau', 'createur')
    classement_cours = []
    
    for cours in courses:
        eleves = Utilisateur.objects.filter(
            role='ELEVE',
            is_active=True,
            classe__niveau=cours.niveau
        )
        total_eleves = eleves.count()
        nb_diff = eleves_en_difficulte(cours.id, seuil=50).count() if total_eleves > 0 else 0
        taux_echec = round((nb_diff / total_eleves) * 100) if total_eleves > 0 else 0
        
        writer.writerow([
            cours.titre,
            cours.niveau.nom,
            cours.createur.get_full_name() if cours.createur else 'Aucun',
            nb_diff,
            total_eleves,
            taux_echec
        ])

    return response
