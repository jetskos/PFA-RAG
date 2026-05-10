from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from .models import Equipment, Ticket
from .forms import TicketForm, EquipmentForm


def _is_htmx(request):
    return request.headers.get('HX-Request') == 'true' or getattr(request, 'htmx', False)


@require_http_methods(['GET', 'POST'])
def inventaire_view(request):
    """Page inventaire avec HTMX pour filtrer les équipements."""
    equipements = Equipment.objects.all()

    # HTMX GET: filter equipments by state
    if _is_htmx(request) and request.method == 'GET' and 'etat' in request.GET:
        etat = request.GET.get('etat')
        if etat and etat != 'TOUS':
            equipements = equipements.filter(etat=etat)
        return render(request, 'logistics/partials/equipements_list.html', {
            'equipements': equipements
        })

    return render(request, 'logistics/inventaire.html', {
        'equipements': equipements,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def tickets_view(request):
    """Page support avec la liste des tickets actifs et résolution HTMX."""
    tickets = Ticket.objects.exclude(statut='RESOLU')

    if _is_htmx(request) and request.method == 'POST':
        ticket_id = request.POST.get('ticket_id')
        if not ticket_id:
            return HttpResponseBadRequest('ticket_id manquant')
        ticket = get_object_or_404(Ticket, id=ticket_id)
        ticket.statut = 'RESOLU'
        ticket.save()
        tickets = Ticket.objects.exclude(statut='RESOLU')
        return render(request, 'logistics/partials/tickets_list.html', {
            'tickets': tickets,
            'resolve_url': reverse('logistics:tickets'),
        })

    return render(request, 'logistics/tickets.html', {
        'tickets': tickets,
        'resolve_url': reverse('logistics:tickets'),
    })


@login_required
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
@require_http_methods(['GET', 'POST'])
def ajouter_equipement(request):
    """Ajouter un équipement via fetch/JS (GET: renvoie le formulaire, POST: sauvegarde et renvoie la liste mise à jour)."""
    if request.method == 'POST':
        form = EquipmentForm(request.POST)
        if form.is_valid():
            form.save()
            equipements = Equipment.objects.all()
            return render(request, 'logistics/partials/equipements_list.html', {'equipements': equipements})
    else:
        form = EquipmentForm()

    return render(request, 'logistics/partials/equipement_form.html', {
        'form': form,
        'action_url': reverse('logistics:ajouter_equipement'),
        'submit_label': 'Ajouter'
    })


@login_required
@require_http_methods(['GET', 'POST'])
def editer_equipement(request, pk):
    """Editer un équipement (GET: formulaire, POST: sauvegarde et retourne la liste)."""
    equip = get_object_or_404(Equipment, pk=pk)

    if request.method == 'POST':
        form = EquipmentForm(request.POST, instance=equip)
        if form.is_valid():
            form.save()
            equipements = Equipment.objects.all()
            return render(request, 'logistics/partials/equipements_list.html', {'equipements': equipements})
    else:
        form = EquipmentForm(instance=equip)

    return render(request, 'logistics/partials/equipement_form.html', {
        'form': form,
        'equipement': equip,
        'action_url': reverse('logistics:editer_equipement', args=[equip.pk]),
        'submit_label': 'Enregistrer'
    })


@login_required
@require_http_methods(['POST'])
def supprimer_equipement(request, pk):
    """Supprimer un équipement et renvoyer la liste mise à jour."""
    equip = get_object_or_404(Equipment, pk=pk)
    equip.delete()
    equipements = Equipment.objects.all()
    return render(request, 'logistics/partials/equipements_list.html', {'equipements': equipements})
