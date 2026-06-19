from rest_framework import permissions

class IsCreateurOrReadOnly(permissions.BasePermission):
    """
    Permission personnalisée qui n'autorise la modification d'un cours
    ou d'un chapitre qu'à son créateur (ou à un administrateur).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and (
            request.user.is_superuser or
            getattr(request.user, 'role', None) in ('ADMIN', 'FORMATEUR')
        )

    def has_object_permission(self, request, view, obj):
        # SAFE_METHODS (GET, HEAD, OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            return True

        # Admin / Superuser
        if request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN':
            return True

        # Check createur directly
        if hasattr(obj, 'createur') and obj.createur is not None:
            return obj.createur == request.user

        # Check owner of the related course (e.g. for Chapitre or Devoir)
        if hasattr(obj, 'cours') and obj.cours is not None:
            if hasattr(obj.cours, 'createur'):
                return obj.cours.createur == request.user

        if hasattr(obj, 'chapitre') and obj.chapitre is not None:
            if hasattr(obj.chapitre, 'cours') and obj.chapitre.cours is not None:
                if hasattr(obj.chapitre.cours, 'createur'):
                    return obj.chapitre.cours.createur == request.user

        return False
