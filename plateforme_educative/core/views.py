from django.shortcuts import render
from django.urls import reverse


def home_view(request):
    """Affiche la page d'accueil avec la progression de l'étudiant si connecté."""
    from apprentissage.models import Cours, Chapitre, Document

    context = {
        'stats': {
            'cours': Cours.objects.filter(actif=True).count(),
            'chapitres': Chapitre.objects.filter(actif=True).count(),
            'documents': Document.objects.filter(actif=True).count(),
        }
    }
    
    if request.user.is_authenticated:
        from apprentissage.models import Progression
        progressions = Progression.objects.filter(etudiant=request.user).order_by('-date_derniere_consultation')[:3]

        if progressions:
            context['resume_url'] = reverse('apprentissage:detail_cours', args=[progressions[0].cours.id])
        else:
            context['resume_url'] = reverse('apprentissage:liste_cours')
        
        cours_en_cours = [
            {
                'titre': p.cours.titre,
                'chapitre_actuel': f"{p.chapitres_valides.count()}/{p.cours.chapitres.count()} chapitres",
                'progression': p.pourcentage
                , 'url': reverse('apprentissage:detail_cours', args=[p.cours.id])
            }
            for p in progressions
        ]
        context['cours_en_cours'] = cours_en_cours
    
    return render(request, 'core/home.html', context)