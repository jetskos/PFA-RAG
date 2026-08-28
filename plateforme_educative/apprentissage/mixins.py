"""
Mixins et Décorateurs pour la gestion des permissions par objet (Tâche 8).
Ces classes héritent de AccessMixin et proposent également un décorateur
pour être appliquées facilement aux vues basées sur des fonctions (FBV).

Vues auditées et corrigées :
- apprentissage:espace_formateur : OK (vérifie le rôle FORMATEUR)
- apprentissage:nouveau_cours : OK (vérifie le rôle FORMATEUR)
- apprentissage:editer_cours : CORRIGÉE -> FormateurCoursRequiredMixin
- apprentissage:supprimer_cours : CORRIGÉE -> FormateurCoursRequiredMixin
- apprentissage:gerer_cours : CORRIGÉE -> FormateurCoursRequiredMixin
- apprentissage:ajouter_chapitre : CORRIGÉE -> FormateurCoursRequiredMixin
- apprentissage:gerer_chapitre : CORRIGÉE -> FormateurChapitreRequiredMixin
- apprentissage:editer_chapitre : CORRIGÉE -> FormateurChapitreRequiredMixin
- apprentissage:supprimer_chapitre : CORRIGÉE -> FormateurChapitreRequiredMixin
- apprentissage:ajouter_document : CORRIGÉE -> FormateurChapitreRequiredMixin
- apprentissage:editer_document : CORRIGÉE -> FormateurChapitreRequiredMixin (via document.chapitre)
- apprentissage:supprimer_document : CORRIGÉE -> FormateurChapitreRequiredMixin (via document.chapitre)
- apprentissage:devoir_creer : CORRIGÉE -> FormateurChapitreRequiredMixin
- apprentissage:devoir_editer : CORRIGÉE -> FormateurDevoirRequiredMixin
- apprentissage:devoir_supprimer : CORRIGÉE -> FormateurDevoirRequiredMixin
- apprentissage:soumission_noter : CORRIGÉE -> FormateurDevoirRequiredMixin (via soumission.devoir)
- tuteur_ia:corriger_qcm : CORRIGÉE -> ElevePropreDonneeMixin (via session_id)
- tuteur_ia:resultats_qcm : CORRIGÉE -> ElevePropreDonneeMixin (via session_id)
- analytics:formateur_course_analytics : CORRIGÉE -> FormateurCoursRequiredMixin (via cours_id)
"""

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from functools import wraps

from apprentissage.models import Cours, Chapitre, Devoir, Progression, Soumission, Document
from tuteur_ia.models import SessionQCM

class FormateurCoursRequiredMixin(AccessMixin):
    """
    Vérifie que l'utilisateur est le créateur du Cours.
    """
    allow_admin = True

    def has_permission(self, request, *args, **kwargs):
        # Récupérer l'ID du cours depuis l'URL (pk, cours_id, ou cours_pk)
        cours_id = kwargs.get('pk') or kwargs.get('cours_id') or kwargs.get('cours_pk')
        if not cours_id:
            return False
            
        cours = get_object_or_404(Cours, id=cours_id)
        
        # Admin bypass
        if self.allow_admin and (request.user.role == 'ADMIN' or request.user.is_superuser):
            return True
            
        # Vérification formateur créateur
        return request.user.is_formateur and cours.createur == request.user

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.has_permission(request, *args, **kwargs):
            raise PermissionDenied(_("Vous n'êtes pas le créateur de ce cours."))
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def as_decorator(cls, allow_admin=True):
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):
                if not request.user.is_authenticated:
                    raise PermissionDenied(_("Connexion requise."))
                mixin = cls()
                mixin.allow_admin = allow_admin
                if not mixin.has_permission(request, *args, **kwargs):
                    raise PermissionDenied(_("Vous n'êtes pas le créateur de ce cours."))
                return view_func(request, *args, **kwargs)
            return _wrapped_view
        return decorator


class FormateurChapitreRequiredMixin(AccessMixin):
    """
    Vérifie que l'utilisateur est le créateur du Cours associé au Chapitre (ou au Document).
    """
    allow_admin = True

    def has_permission(self, request, *args, **kwargs):
        chapitre_id = kwargs.get('chapitre_id') or kwargs.get('chapitre_pk') or kwargs.get('pk')
        document_id = kwargs.get('document_id')
        
        if document_id:
            doc = get_object_or_404(Document, id=document_id)
            chapitre = doc.chapitre
        elif chapitre_id:
            chapitre = get_object_or_404(Chapitre, id=chapitre_id)
        else:
            return False
            
        cours = chapitre.cours
        
        if self.allow_admin and (request.user.role == 'ADMIN' or request.user.is_superuser):
            return True
            
        return request.user.is_formateur and cours.createur == request.user

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.has_permission(request, *args, **kwargs):
            raise PermissionDenied(_("Vous n'êtes pas le créateur du cours associé."))
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def as_decorator(cls, allow_admin=True):
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):
                if not request.user.is_authenticated:
                    raise PermissionDenied(_("Connexion requise."))
                mixin = cls()
                mixin.allow_admin = allow_admin
                if not mixin.has_permission(request, *args, **kwargs):
                    raise PermissionDenied(_("Vous n'êtes pas le créateur du cours associé."))
                return view_func(request, *args, **kwargs)
            return _wrapped_view
        return decorator


class FormateurDevoirRequiredMixin(AccessMixin):
    """
    Vérifie que l'utilisateur est le créateur du Cours associé au Devoir (ou à la Soumission).
    """
    allow_admin = True

    def has_permission(self, request, *args, **kwargs):
        devoir_id = kwargs.get('devoir_id') or kwargs.get('devoir_pk') or kwargs.get('pk')
        soumission_id = kwargs.get('soumission_id')
        
        if soumission_id:
            soumission = get_object_or_404(Soumission, id=soumission_id)
            devoir = soumission.devoir
        elif devoir_id:
            devoir = get_object_or_404(Devoir, id=devoir_id)
        else:
            return False
            
        cours = devoir.chapitre.cours
        
        if self.allow_admin and (request.user.role == 'ADMIN' or request.user.is_superuser):
            return True
            
        # [SÉCURITÉ] Log de debug supprimé — ne jamais exposer les emails dans les logs en production.
        return request.user.is_formateur and cours.createur == request.user

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.has_permission(request, *args, **kwargs):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à agir sur ce devoir."))
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def as_decorator(cls, allow_admin=True):
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):
                if not request.user.is_authenticated:
                    raise PermissionDenied(_("Connexion requise."))
                mixin = cls()
                mixin.allow_admin = allow_admin
                if not mixin.has_permission(request, *args, **kwargs):
                    raise PermissionDenied(_("Vous n'êtes pas autorisé à agir sur ce devoir."))
                return view_func(request, *args, **kwargs)
            return _wrapped_view
        return decorator


class ElevePropreDonneeMixin(AccessMixin):
    """
    Vérifie que l'objet cible (Progression, Soumission, SessionQCM) appartient à l'étudiant connecté.
    """
    allow_admin = True

    def has_permission(self, request, *args, **kwargs):
        # Bypass admin
        if self.allow_admin and (request.user.role == 'ADMIN' or request.user.is_superuser):
            return True
            
        # Chercher l'objet cible selon les clés d'URL
        soumission_id = kwargs.get('soumission_id')
        session_id = kwargs.get('session_id')
        progression_id = kwargs.get('progression_id')
        pk = kwargs.get('pk')
        
        # Essayer de deviner l'objet selon le contexte ou la valeur pk
        if soumission_id:
            obj = get_object_or_404(Soumission, id=soumission_id)
            return obj.etudiant == request.user
        elif session_id:
            obj = get_object_or_404(SessionQCM, id=session_id)
            return obj.etudiant == request.user
        elif progression_id:
            obj = get_object_or_404(Progression, id=progression_id)
            return obj.etudiant == request.user
        elif pk:
            # On tente de voir si la pk correspond à un de nos types
            for model in [Soumission, SessionQCM, Progression]:
                try:
                    obj = model.objects.get(id=pk)
                    return obj.etudiant == request.user
                except (model.DoesNotExist, ValueError, TypeError):
                    continue
        return False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.has_permission(request, *args, **kwargs):
            raise PermissionDenied(_("Accès interdit à ces données personnelles."))
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def as_decorator(cls, allow_admin=True):
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):
                if not request.user.is_authenticated:
                    raise PermissionDenied(_("Connexion requise."))
                mixin = cls()
                mixin.allow_admin = allow_admin
                if not mixin.has_permission(request, *args, **kwargs):
                    raise PermissionDenied(_("Accès interdit à ces données personnelles."))
                return view_func(request, *args, **kwargs)
            return _wrapped_view
        return decorator
