from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.contrib.auth.decorators import login_required, user_passes_test
from django.urls import reverse

from .models import Equipment, Ticket, Workshop, DemandeMateriel
from .forms import TicketForm, EquipmentForm, WorkshopForm, DemandeMaterielForm
from .excel_export import (
    export_equipements_excel,
    export_ateliers_excel,
    export_demandes_excel,
    export_tickets_excel
)
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _


def _is_htmx(request):
    is_htmx_req = request.headers.get('HX-Request') == 'true' or getattr(request, 'htmx', False)
    return is_htmx_req and request.headers.get('HX-Target') != 'zone-principale'


@login_required
@require_http_methods(['GET', 'POST'])
def creer_ticket_formateur(request, demande_id):
    """Permet à un formateur de signaler une panne sur un équipement qu'il a emprunté."""
    demande = get_object_or_404(DemandeMateriel, id=demande_id, formateur=request.user, statut='APPROVED')
    
    if request.method == 'POST':
        titre = request.POST.get('titre')
        description = request.POST.get('description')
        if titre and description:
            Ticket.objects.create(
                titre=titre,
                description=description,
                equipement=demande.equipement,
                atelier=demande.atelier_cible,
                ouvert_par=request.user,
                statut='OUVERT'
            )
            # Optionnel: changer le statut de la demande ? Pour l'instant on garde juste le ticket.
            return HttpResponse('<div class="alert alert-success">Ticket créé avec succès ! La logistique est prévenue.</div>')
        return HttpResponseBadRequest("Titre et description requis.")
    
    # Rendu du formulaire HTMX
    return render(request, 'logistics/partials/ticket_formateur_form.html', {'demande': demande})


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
def inventaire_view(request):
    """Page inventaire avec HTMX pour filtrer les équipements."""
    from django.db.models import Sum, F
    equipements = Equipment.objects.all()

    # Calculate stats based on new model (stock_total, stock_disponible, est_actif)
    stock_agg = equipements.aggregate(
        total_dispo=Sum('stock_disponible'),
        total_physique=Sum('stock_total')
    )
    total_dispo = stock_agg['total_dispo'] or 0
    total_physique = stock_agg['total_physique'] or 0
    en_maintenance = total_physique - total_dispo

    equipements_en_alerte = sum(1 for e in equipements if e.en_alerte and e.est_actif)

    # Appliquer les filtres
    etat = request.GET.get('etat', 'TOUS')
    q = request.GET.get('q', '').strip()
    
    if etat == 'DISPONIBLE':
        equipements = equipements.filter(est_actif=True)
    elif etat == 'EN_PANNE':
        equipements = equipements.filter(est_actif=False)
        
    if q:
        from django.db.models import Q
        equipements = equipements.filter(Q(nom__icontains=q) | Q(reference__icontains=q))

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(equipements, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
            
    if _is_htmx(request) and request.method == 'GET':
        return render(request, 'logistics/partials/equipements_list.html', {
            'equipements': page_obj,
            'page_obj': page_obj
        })

    return render(request, 'logistics/inventaire.html', {
        'equipements': page_obj,
        'page_obj': page_obj,
        'equipements_disponibles': total_dispo,
        'equipements_maintenance': en_maintenance,
        'equipements_en_panne': equipements_en_alerte,
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
@require_http_methods(['GET', 'POST'])
def tickets_view(request):
    """Page support avec la liste des tickets actifs et résolution HTMX."""
    tickets = Ticket.objects.exclude(statut='RESOLU')

    if _is_htmx(request) and request.method == 'POST':
        ticket_id = request.POST.get('ticket_id')
        if not ticket_id:
            return HttpResponseBadRequest('ticket_id manquant')
        # Only staff/formateurs can mark tickets resolved
        if not (request.user.is_staff or getattr(request.user, 'is_formateur', False)):
            return HttpResponseForbidden(_('Permission refusée'))
        ticket = get_object_or_404(Ticket, id=ticket_id)
        ticket.statut = 'RESOLU'
        ticket.save()
        tickets = Ticket.objects.exclude(statut='RESOLU')
        return render(request, 'logistics/partials/tickets_list.html', {
            'tickets': tickets,
            'resolve_url': reverse('logistics:tickets'),
        })

    # Stats for UI
    all_tickets = Ticket.objects.all()
    tickets_en_attente = all_tickets.filter(statut='OUVERT').count()
    tickets_en_cours = all_tickets.filter(statut='EN_COURS').count()
    tickets_resolus = all_tickets.filter(statut='RESOLU').count()

    return render(request, 'logistics/tickets.html', {
        'tickets': tickets,
        'resolve_url': reverse('logistics:tickets'),
        'tickets_en_attente': tickets_en_attente,
        'tickets_en_cours': tickets_en_cours,
        'tickets_resolus': tickets_resolus,
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
@require_http_methods(['GET', 'POST'])
def nuevo_ticket(request):
    """Create a new ticket. User and status are set server-side."""
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.ouvert_par = request.user
            ticket.statut = 'OUVERT'
            ticket.save()
            return redirect('logistics:tickets')
    else:
        form = TicketForm()
    
    return render(request, 'logistics/ticket_form.html', {'form': form})


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
@require_http_methods(['GET', 'POST'])
def ajouter_equipement(request):
    """Ajouter un équipement (GET: renvoie le formulaire, POST: sauvegarde et renvoie la liste mise à jour)."""
    if request.method == 'POST':
        form = EquipmentForm(request.POST)
        if form.is_valid():
            form.save()
            equipements = Equipment.objects.all()
            from django.core.paginator import Paginator
            paginator = Paginator(equipements, 15)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            response = render(request, 'logistics/partials/equipements_list.html', {'equipements': page_obj, 'page_obj': page_obj})
            response['HX-Trigger'] = 'closeModal'
            return response
        else:
            response = render(request, 'logistics/partials/equipement_form.html', {
                'form': form,
                'action_url': reverse('logistics:ajouter_equipement'),
                'submit_label': 'Ajouter'
            })
            response['HX-Retarget'] = '#form-equipement-container'
            return response
    else:
        form = EquipmentForm()

    return render(request, 'logistics/partials/equipement_form.html', {
        'form': form,
        'action_url': reverse('logistics:ajouter_equipement'),
        'submit_label': 'Ajouter'
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
@require_http_methods(['GET', 'POST'])
def editer_equipement(request, pk):
    """Editer un équipement (GET: formulaire, POST: sauvegarde et retourne la liste)."""
    equip = get_object_or_404(Equipment, pk=pk)

    if request.method == 'POST':
        form = EquipmentForm(request.POST, instance=equip)
        if form.is_valid():
            form.save()
            equipements = Equipment.objects.all()
            from django.core.paginator import Paginator
            paginator = Paginator(equipements, 15)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            response = render(request, 'logistics/partials/equipements_list.html', {'equipements': page_obj, 'page_obj': page_obj})
            response['HX-Trigger'] = 'closeModal'
            return response
        else:
            response = render(request, 'logistics/partials/equipement_form.html', {
                'form': form,
                'equipement': equip,
                'action_url': reverse('logistics:editer_equipement', args=[equip.pk]),
                'submit_label': 'Enregistrer'
            })
            response['HX-Retarget'] = '#form-equipement-container'
            return response
    else:
        form = EquipmentForm(instance=equip)

    return render(request, 'logistics/partials/equipement_form.html', {
        'form': form,
        'equipement': equip,
        'action_url': reverse('logistics:editer_equipement', args=[equip.pk]),
        'submit_label': 'Enregistrer'
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
@require_http_methods(['POST'])
def supprimer_equipement(request, pk):
    """Supprimer un équipement et renvoyer la liste mise à jour."""
    equip = get_object_or_404(Equipment, pk=pk)
    equip.est_actif = False
    equip.save()
    equipements = Equipment.objects.all()
    from django.core.paginator import Paginator
    paginator = Paginator(equipements, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'logistics/partials/equipements_list.html', {'equipements': page_obj, 'page_obj': page_obj})


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
def ateliers_view(request):
    from django.utils import timezone
    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
        ateliers = Workshop.objects.select_related('createur', 'tuteur').all()
    else:
        ateliers = Workshop.objects.select_related('createur', 'tuteur').filter(createur=request.user)

    # Stat computations
    now = timezone.now()
    ateliers_total = ateliers.count()
    ateliers_annules = ateliers.filter(est_annule=True).count()
    ateliers_en_cours = ateliers.filter(date_debut__lte=now, date_fin__gte=now, est_annule=False).count()
    ateliers_a_venir = ateliers.filter(date_debut__gt=now, est_annule=False).count()

    # Appliquer les filtres
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        ateliers = ateliers.filter(Q(titre__icontains=q) | Q(salle__icontains=q))

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(ateliers, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    if _is_htmx(request) and request.method == 'GET':
        return render(request, 'logistics/partials/ateliers_list.html', {'ateliers': page_obj, 'page_obj': page_obj})

    return render(request, 'logistics/ateliers.html', {
        'ateliers': page_obj,
        'page_obj': page_obj,
        'ateliers_total': ateliers_total,
        'ateliers_en_cours': ateliers_en_cours,
        'ateliers_a_venir': ateliers_a_venir,
        'ateliers_annules': ateliers_annules,
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
@require_http_methods(['GET', 'POST'])
def ajouter_atelier(request):
    if request.method == 'POST':
        form = WorkshopForm(request.POST)
        if form.is_valid():
            atelier = form.save(commit=False)
            atelier.createur = request.user
            if not atelier.tuteur:
                atelier.tuteur = request.user
            atelier.save()
            if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
                ateliers = Workshop.objects.all()
            else:
                ateliers = Workshop.objects.filter(createur=request.user)
            from django.core.paginator import Paginator
            paginator = Paginator(ateliers, 15)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            return render(request, 'logistics/partials/ateliers_list.html', {'ateliers': page_obj, 'page_obj': page_obj})
        else:
            response = render(request, 'logistics/partials/atelier_form.html', {
                'form': form,
                'action_url': reverse('logistics:ajouter_atelier'),
                'submit_label': 'Ajouter'
            })
            response['HX-Retarget'] = '#form-atelier-container'
            return response
    else:
        form = WorkshopForm(initial={'tuteur': request.user})

    return render(request, 'logistics/partials/atelier_form.html', {
        'form': form,
        'action_url': reverse('logistics:ajouter_atelier'),
        'submit_label': 'Ajouter'
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
@require_http_methods(['GET', 'POST'])
def editer_atelier(request, pk):
    atelier = get_object_or_404(Workshop, pk=pk)

    if not request.user.is_staff and atelier.createur != request.user:
        return HttpResponseForbidden(_("Vous n'êtes pas autorisé à modifier cet atelier."))

    if request.method == 'POST':
        form = WorkshopForm(request.POST, instance=atelier)
        if form.is_valid():
            form.save()
            if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
                ateliers = Workshop.objects.all()
            else:
                ateliers = Workshop.objects.filter(createur=request.user)
            from django.core.paginator import Paginator
            paginator = Paginator(ateliers, 15)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            return render(request, 'logistics/partials/ateliers_list.html', {'ateliers': page_obj, 'page_obj': page_obj})
        else:
            response = render(request, 'logistics/partials/atelier_form.html', {
                'form': form,
                'atelier': atelier,
                'action_url': reverse('logistics:editer_atelier', args=[atelier.pk]),
                'submit_label': 'Enregistrer'
            })
            response['HX-Retarget'] = '#form-atelier-container'
            return response
    else:
        form = WorkshopForm(instance=atelier)

    return render(request, 'logistics/partials/atelier_form.html', {
        'form': form,
        'atelier': atelier,
        'action_url': reverse('logistics:editer_atelier', args=[atelier.pk]),
        'submit_label': 'Enregistrer'
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
@require_http_methods(['POST'])
def supprimer_atelier(request, pk):
    atelier = get_object_or_404(Workshop, pk=pk)
    
    if not request.user.is_staff and atelier.createur != request.user:
        return HttpResponseForbidden(_("Vous n'êtes pas autorisé à supprimer cet atelier."))

    if atelier.demandes_materiel.filter(statut='APPROVED').exists():
        return HttpResponseBadRequest("Interdiction de supprimer cet atelier, il est lié à une Demande de Matériel validée.")

    if atelier.tickets.exists():
        return HttpResponseBadRequest("Cet atelier est lié à des tickets et ne peut pas être supprimé.")

    # Soft Delete
    atelier.est_annule = True
    atelier.save()

    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
        ateliers = Workshop.objects.all()
    else:
        ateliers = Workshop.objects.filter(createur=request.user)
    from django.core.paginator import Paginator
    paginator = Paginator(ateliers, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'logistics/partials/ateliers_list.html', {'ateliers': page_obj, 'page_obj': page_obj})


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
def demandes_view(request):
    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
        demandes = DemandeMateriel.objects.select_related('formateur', 'equipement', 'atelier_cible').all()
    else:
        demandes = DemandeMateriel.objects.select_related('formateur', 'equipement', 'atelier_cible').filter(formateur=request.user)

    # Stat computations
    demandes_total = demandes.count()
    demandes_en_attente = demandes.filter(statut='PENDING').count()
    demandes_approuvees = demandes.filter(statut='APPROVED').count()
    demandes_rejetees = demandes.filter(statut='REJECTED').count()

    # Appliquer les filtres
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    
    if statut:
        demandes = demandes.filter(statut=statut)
        
    if q:
        from django.db.models import Q
        demandes = demandes.filter(
            Q(formateur__first_name__icontains=q) | 
            Q(formateur__last_name__icontains=q) |
            Q(equipement__nom__icontains=q) |
            Q(atelier_cible__titre__icontains=q)
        )

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(demandes, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    if _is_htmx(request) and request.method == 'GET':
        return render(request, 'logistics/partials/demandes_list.html', {'demandes': page_obj, 'page_obj': page_obj})

    return render(request, 'logistics/demandes.html', {
        'demandes': page_obj,
        'page_obj': page_obj,
        'demandes_total': demandes_total,
        'demandes_en_attente': demandes_en_attente,
        'demandes_approuvees': demandes_approuvees,
        'demandes_rejetees': demandes_rejetees,
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
@require_http_methods(['GET', 'POST'])
def ajouter_demande(request):
    if request.method == 'POST':
        atelier_id = request.POST.get('atelier_cible')
        equipements_ids = request.POST.getlist('equipement[]')
        quantites = request.POST.getlist('quantite[]')
        
        if atelier_id and equipements_ids:
            atelier = get_object_or_404(Workshop, pk=atelier_id)
            for eq_id, q in zip(equipements_ids, quantites):
                if eq_id and q and int(q) > 0:
                    eq = get_object_or_404(Equipment, pk=eq_id)
                    DemandeMateriel.objects.create(
                        formateur=request.user,
                        equipement=eq,
                        atelier_cible=atelier,
                        quantite=int(q),
                        statut='PENDING'
                    )
            
            if 'dashboard' in request.META.get('HTTP_REFERER', ''):
                from django.http import HttpResponse
                response = HttpResponse()
                response['HX-Redirect'] = reverse('logistics:demandes')
                return response
                
            if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
                demandes = DemandeMateriel.objects.all()
            else:
                demandes = DemandeMateriel.objects.filter(formateur=request.user)
            from django.core.paginator import Paginator
            paginator = Paginator(demandes, 15)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            return render(request, 'logistics/partials/demandes_list.html', {'demandes': page_obj, 'page_obj': page_obj})
        
        # If error, return to form (could add messages here)
        return HttpResponseBadRequest("Données invalides")

    else:
        # Afficher tous les ateliers actifs, même pour les formateurs, pour éviter un menu vide.
        ateliers = Workshop.objects.filter(est_annule=False).order_by('-date_debut')
        equipements = Equipment.objects.filter(est_actif=True).order_by('nom')

    return render(request, 'logistics/partials/demande_form.html', {
        'ateliers': ateliers,
        'equipements': equipements,
        'action_url': reverse('logistics:ajouter_demande'),
        'submit_label': 'Envoyer la demande de lot'
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
@require_http_methods(['GET', 'POST'])
def editer_demande(request, pk):
    demande = get_object_or_404(DemandeMateriel, pk=pk)

    if not request.user.is_staff and demande.formateur != request.user:
        return HttpResponseForbidden(_("Vous n'êtes pas autorisé à modifier cette demande."))
    
    if demande.statut != 'PENDING':
        return HttpResponseBadRequest("Impossible de modifier une demande qui n'est plus en attente.")

    if request.method == 'POST':
        form = DemandeMaterielForm(request.POST, instance=demande, request=request)
        if form.is_valid():
            form.save()
            if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
                demandes = DemandeMateriel.objects.all()
            else:
                demandes = DemandeMateriel.objects.filter(formateur=request.user)
            from django.core.paginator import Paginator
            paginator = Paginator(demandes, 15)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            return render(request, 'logistics/partials/demandes_list.html', {'demandes': page_obj, 'page_obj': page_obj})
        else:
            response = render(request, 'logistics/partials/demande_form.html', {
                'form': form,
                'demande': demande,
                'action_url': reverse('logistics:editer_demande', args=[demande.pk]),
                'submit_label': 'Enregistrer'
            })
            response['HX-Retarget'] = '#form-demande-container'
            return response
    else:
        form = DemandeMaterielForm(instance=demande, request=request)

    return render(request, 'logistics/partials/demande_form.html', {
        'form': form,
        'demande': demande,
        'action_url': reverse('logistics:editer_demande', args=[demande.pk]),
        'submit_label': 'Enregistrer'
    })


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
@require_http_methods(['POST'])
def supprimer_demande(request, pk):
    demande = get_object_or_404(DemandeMateriel, pk=pk)
    
    if not request.user.is_staff and demande.formateur != request.user:
        return HttpResponseForbidden(_("Vous n'êtes pas autorisé à supprimer cette demande."))

    if demande.statut != 'PENDING':
        return HttpResponseBadRequest("Seules les demandes en attente peuvent être supprimées.")

    demande.delete()

    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
        demandes = DemandeMateriel.objects.all()
    else:
        demandes = DemandeMateriel.objects.filter(formateur=request.user)
    from django.core.paginator import Paginator
    paginator = Paginator(demandes, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'logistics/partials/demandes_list.html', {'demandes': page_obj, 'page_obj': page_obj})


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
@require_http_methods(['POST'])
@transaction.atomic
def changer_statut_demande(request, pk):
    demande = get_object_or_404(DemandeMateriel, pk=pk)
    nouveau_statut = request.POST.get('statut')
    
    if nouveau_statut not in dict(DemandeMateriel.STATUT_CHOICES).keys():
        return HttpResponseBadRequest("Statut invalide.")

    # Logic for stock
    if demande.statut == 'PENDING' and nouveau_statut == 'APPROVED':
        if demande.equipement.stock_disponible >= demande.quantite:
            demande.equipement.stock_disponible -= demande.quantite
            demande.equipement.save()
        else:
            return HttpResponseBadRequest("Stock insuffisant pour approuver cette demande.")
    
    elif demande.statut == 'APPROVED' and nouveau_statut in ['RETURNED', 'REJECTED']:
        demande.equipement.stock_disponible += demande.quantite
        demande.equipement.save()
        
    demande.statut = nouveau_statut
    demande.save()

    # Notifier le formateur de la décision (notification in-app)
    try:
        from accounts.notifications import notifier
        statut_labels = {'APPROVED': 'approuvée ✅', 'REJECTED': 'rejetée ❌', 'RETURNED': 'marquée comme retournée 🔄'}
        label = statut_labels.get(nouveau_statut)
        if label:
            notifier(
                destinataire=demande.formateur,
                type='DEMANDE_TRAITEE',
                titre='Votre demande a été traitée',
                message=f'Votre demande de {demande.quantite}x {demande.equipement.nom} a été {label}.',
                url=reverse('logistics:demandes'),
            )
    except Exception as e:
        print(f"Erreur notification: {e}")

    # Envoyer un email au formateur via SMTP
    if nouveau_statut in ('APPROVED', 'REJECTED', 'RETURNED'):
        try:
            from django.core.mail import EmailMultiAlternatives
            from django.template.loader import render_to_string
            from django.utils import timezone
            from django.conf import settings

            site_url = request.build_absolute_uri('/').rstrip('/')
            formateur = demande.formateur

            ctx = {
                'statut': nouveau_statut,
                'formateur_nom': formateur.get_full_name() or formateur.email,
                'equipement_nom': demande.equipement.nom,
                'quantite': demande.quantite,
                'atelier_nom': demande.atelier_cible.titre if demande.atelier_cible else None,
                'site_url': site_url,
                'date_envoi': timezone.now().strftime('%d/%m/%Y à %Hh%M'),
            }

            sujet_map = {
                'APPROVED': f'✅ Demande approuvée — {demande.quantite}x {demande.equipement.nom}',
                'REJECTED': f'❌ Demande rejetée — {demande.quantite}x {demande.equipement.nom}',
                'RETURNED': f'🔄 Équipement retourné — {demande.quantite}x {demande.equipement.nom}',
            }
            sujet = sujet_map[nouveau_statut]

            html_body = render_to_string('logistics/emails/demande_traitee.html', ctx)

            text_body = (
                f"Bonjour {ctx['formateur_nom']},\n\n"
                f"Votre demande de {demande.quantite}x {demande.equipement.nom} "
                f"a été {statut_labels.get(nouveau_statut, nouveau_statut)}.\n\n"
                f"Consultez vos demandes : {site_url}/logistics/demandes/\n\n"
                f"— EduTech"
            )

            email = EmailMultiAlternatives(
                subject=sujet,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[formateur.email],
            )
            email.attach_alternative(html_body, 'text/html')
            email.send(fail_silently=False)
        except Exception as e:
            print(f"Erreur envoi email demande: {e}")

    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN':
        demandes = DemandeMateriel.objects.all()
    else:
        demandes = DemandeMateriel.objects.filter(formateur=request.user)
    from django.core.paginator import Paginator
    paginator = Paginator(demandes, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'logistics/partials/demandes_list.html', {'demandes': page_obj, 'page_obj': page_obj})


@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
def exporter_equipements(request):
    """Exporter les équipements en Excel formaté."""
    equipements = Equipment.objects.all()
    excel_bytes, filename = export_equipements_excel(equipements)
    
    response = HttpResponse(
        excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
def exporter_ateliers(request):
    """Exporter les ateliers en Excel formaté."""
    ateliers = Workshop.objects.select_related('createur', 'tuteur').all()
    excel_bytes, filename = export_ateliers_excel(ateliers)
    
    response = HttpResponse(
        excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN' or getattr(u, 'is_formateur', False) or getattr(u, 'role', '') == 'FORMATEUR')
def exporter_demandes(request):
    """Exporter les demandes de matériel en Excel formaté."""
    demandes = DemandeMateriel.objects.select_related('formateur', 'equipement', 'atelier_cible').all()
    excel_bytes, filename = export_demandes_excel(demandes)
    
    response = HttpResponse(
        excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@user_passes_test(lambda u: getattr(u, 'is_staff', False) or getattr(u, 'role', '') == 'ADMIN')
def exporter_tickets(request):
    """Exporter les tickets en Excel formaté."""
    tickets = Ticket.objects.select_related('equipement', 'atelier', 'ouvert_par').all()
    excel_bytes, filename = export_tickets_excel(tickets)
    
    response = HttpResponse(
        excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
