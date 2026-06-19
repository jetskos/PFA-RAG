import csv
from django.shortcuts import render
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.dateparse import parse_date
from .models import JournalAudit

@login_required
def audit_log_view(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        raise PermissionDenied("Accès réservé aux administrateurs.")

    queryset = JournalAudit.objects.all().select_related('utilisateur')

    # Extraction des filtres depuis la requête GET
    action_filter = request.GET.get('action')
    user_filter = request.GET.get('user')
    obj_type_filter = request.GET.get('object_type')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    if action_filter:
        queryset = queryset.filter(action=action_filter)
    if user_filter:
        queryset = queryset.filter(
            Q(utilisateur__email__icontains=user_filter) |
            Q(utilisateur__username__icontains=user_filter)
        )
    if obj_type_filter:
        queryset = queryset.filter(type_objet__icontains=obj_type_filter)
    
    if date_debut:
        parsed_debut = parse_date(date_debut)
        if parsed_debut:
            queryset = queryset.filter(date_action__date__gte=parsed_debut)
            
    if date_fin:
        parsed_fin = parse_date(date_fin)
        if parsed_fin:
            queryset = queryset.filter(date_action__date__lte=parsed_fin)

    # Pagination : 25 par page
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'action_choices': JournalAudit.ACTIONS,
        'action_filter': action_filter,
        'user_filter': user_filter,
        'obj_type_filter': obj_type_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'titre_page': "Journal d'Audit de la Plateforme",
    }
    return render(request, 'audit/audit_log.html', context)

@login_required
def export_audit_csv(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        raise PermissionDenied("Accès réservé aux administrateurs.")

    queryset = JournalAudit.objects.all().select_related('utilisateur')

    action_filter = request.GET.get('action')
    user_filter = request.GET.get('user')
    obj_type_filter = request.GET.get('object_type')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    if action_filter:
        queryset = queryset.filter(action=action_filter)
    if user_filter:
        queryset = queryset.filter(
            Q(utilisateur__email__icontains=user_filter) |
            Q(utilisateur__username__icontains=user_filter)
        )
    if obj_type_filter:
        queryset = queryset.filter(type_objet__icontains=obj_type_filter)
    
    if date_debut:
        parsed_debut = parse_date(date_debut)
        if parsed_debut:
            queryset = queryset.filter(date_action__date__gte=parsed_debut)
            
    if date_fin:
        parsed_fin = parse_date(date_fin)
        if parsed_fin:
            queryset = queryset.filter(date_action__date__lte=parsed_fin)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="journal_audit.csv"'
    response.write('\ufeff') # BOM Excel

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Date/Heure', 'Utilisateur', 'Action', 'Type Objet', 'ID Objet', 'Representation', 'Details', 'Adresse IP'])

    for log in queryset:
        user_str = log.utilisateur.email if log.utilisateur else 'Anonyme'
        writer.writerow([
            log.date_action.strftime('%d/%m/%Y %H:%M:%S'),
            user_str,
            log.get_action_display(),
            log.type_objet,
            log.id_objet or '',
            log.representation or '',
            log.details or '',
            log.adresse_ip or ''
        ])

    return response
