from django.utils.cache import patch_vary_headers

class HTMXHistoryRestoreMiddleware:
    """
    Middleware pour corriger la restauration d'historique HTMX et la mise en cache.
    1. Si HTMX demande une restauration d'historique (HX-History-Restore-Request),
       on désactive l'en-tête HX-Request pour forcer Django à renvoyer la page complète.
    2. On ajoute l'en-tête 'Vary: HX-Request' à toutes les réponses pour éviter
       que le navigateur ne serve des fragments partiels en cache lors d'un rafraîchissement (F5).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get('HTTP_HX_HISTORY_RESTORE_REQUEST') == 'true':
            request.META.pop('HTTP_HX_REQUEST', None)
            
        response = self.get_response(request)
        
        # S'assurer que le cache varie selon si c'est du HTMX ou non
        patch_vary_headers(response, ('HX-Request',))
        
        # Si la requête est une requête HTMX (qui a renvoyé un fragment partiel),
        # on interdit sa mise en cache pour éviter que le navigateur ne le serve lors d'un rafraîchissement (F5).
        if request.headers.get('HX-Request') == 'true':
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
        return response


