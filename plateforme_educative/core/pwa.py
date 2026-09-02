"""Progressive Web App : manifeste, service worker et page hors-ligne.

Ces trois ressources sont servies à la racine du site (hors `i18n_patterns`,
donc sans préfixe de langue) pour que le service worker ait une portée `/`
complète. Le manifeste et le SW sont rendus comme des templates Django afin
que les URL `{% static %}` (hashées en production par ManifestStaticFilesStorage)
soient correctes.
"""
import json
import os

from django.http import HttpResponse
from django.templatetags.static import static
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.shortcuts import render

# Incrémenter à chaque changement de la logique de cache du service worker.
SW_CACHE_VERSION = "v10"


@require_GET
@cache_control(max_age=0, no_cache=True, must_revalidate=True)
def service_worker(request):
    body = render(
        request,
        "pwa/service-worker.js",
        {"cache_version": SW_CACHE_VERSION},
        content_type="application/javascript; charset=utf-8",
    )
    # Autorise une portée racine même si le fichier était servi ailleurs.
    body["Service-Worker-Allowed"] = "/"
    return body


@require_GET
@cache_control(max_age=3600)
def manifest(request):
    return render(
        request,
        "pwa/manifest.webmanifest",
        content_type="application/manifest+json; charset=utf-8",
    )


@require_GET
def offline(request):
    return render(request, "pwa/offline.html")


@require_GET
@cache_control(max_age=3600)
def assetlinks(request):
    """
    Digital Asset Links — sert `/.well-known/assetlinks.json`.

    Nécessaire pour empaqueter la PWA en application Android (TWA / Bubblewrap) :
    Android vérifie que la clé de signature de l'APK est bien déclarée par le
    domaine. Sans ça, l'app affiche une barre d'URL au lieu du plein écran.

    Renseigner via variables d'environnement (valeurs données par Bubblewrap
    à la création du keystore) :
        TWA_PACKAGE_NAME=net.ddns.smartbeam.edutech
        TWA_SHA256_CERT_FINGERPRINTS=AA:BB:CC:...   (plusieurs → séparés par des virgules)
    """
    fingerprints = [
        fp.strip()
        for fp in os.getenv("TWA_SHA256_CERT_FINGERPRINTS", "").replace(";", ",").split(",")
        if fp.strip()
    ]
    package = os.getenv("TWA_PACKAGE_NAME", "").strip()

    statements = []
    if package and fingerprints:
        statements.append({
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package,
                "sha256_cert_fingerprints": fingerprints,
            },
        })

    return HttpResponse(
        json.dumps(statements, indent=2),
        content_type="application/json",
    )
