"""
Utilitaires partagés entre apps — détection de connectivité internet.

Utilisé pour les fonctionnalités hybrides en ligne/hors-ligne (LLM Groq/Ollama,
vidéo YouTube/MP4 local) : un même mécanisme de test réseau, mis en cache par
hôte pour ne pas ralentir chaque requête avec un aller-retour réseau.
"""
import socket
import time

_connectivity_cache = {}


def has_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0, ttl: float = 30.0) -> bool:
    """
    Teste rapidement l'accès à un hôte distant (connexion TCP), avec mise en
    cache de `ttl` secondes par (host, port) pour éviter de re-tester le
    réseau à chaque appel.
    """
    cache_key = (host, port)
    now = time.time()
    entry = _connectivity_cache.get(cache_key)
    if entry is not None and (now - entry["checked_at"]) < ttl:
        return entry["online"]

    try:
        socket.create_connection((host, port), timeout=timeout).close()
        online = True
    except OSError:
        online = False

    _connectivity_cache[cache_key] = {"online": online, "checked_at": now}
    return online
