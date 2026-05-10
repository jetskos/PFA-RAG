from django.shortcuts import render


def home_view(request):
    """Affiche la page d'accueil avec la progression de l'étudiant si connecté."""
    context = {}
    
    if request.user.is_authenticated:
        from apprentissage.models import Progression
        progressions = Progression.objects.filter(etudiant=request.user).order_by('-date_derniere_consultation')[:3]
        
        cours_en_cours = [
            {
                'titre': p.cours.titre,
                'chapitre_actuel': f"{p.chapitres_valides.count()}/{p.cours.chapitres.count()} chapitres",
                'progression': p.pourcentage
            }
            for p in progressions
        ]
        context['cours_en_cours'] = cours_en_cours
    
    return render(request, 'core/home.html', context)