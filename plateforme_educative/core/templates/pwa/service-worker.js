{% load static %}/* EduTech — Service Worker ({{ cache_version }})
   Stratégies :
   - navigation (pages HTML) : réseau d'abord, repli sur le cache puis page hors-ligne
   - statiques /static/ (noms hashés) : cache d'abord
   - images /media/ : stale-while-revalidate
   - tout le reste (POST, API IA, i18n, admin, vidéo/Range) : réseau seul, jamais mis en cache
*/
const VERSION = "{{ cache_version }}";
const PRECACHE = "edutech-precache-" + VERSION;
const RUNTIME = "edutech-runtime-" + VERSION;
const PAGES = "edutech-pages-" + VERSION;
const OFFLINE_URL = "/offline/";
const MAX_PAGES = 40;
const MAX_MEDIA = 60;

const PRECACHE_URLS = [
  OFFLINE_URL,
  "{% static 'core/css/base.css' %}",
  "{% static 'core/css/components.css' %}",
  "{% static 'core/css/responsive.css' %}",
  "{% static 'core/css/apprentissage.css' %}",
  "{% static 'core/css/tuteur.css' %}",
  "{% static 'core/css/formateur.css' %}",
  "{% static 'vendor/fonts/inter.css' %}",
  "{% static 'vendor/fonts/jakarta.css' %}",
  "{% static 'vendor/tabler-icons/tabler-icons.min.css' %}",
  "{% static 'vendor/htmx/htmx.min.js' %}",
  "{% static 'images/pwa/icon-192.png' %}",
  "{% static 'images/pwa/icon-512.png' %}",
  "{% static 'images/logo_white.png' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(PRECACHE)
      // ajout individuel : un asset 404 ne doit pas faire échouer tout le précache
      .then((cache) => Promise.allSettled(
        PRECACHE_URLS.map((u) => cache.add(new Request(u, { cache: "reload" })))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith("edutech-") && !k.endsWith(VERSION))
            .map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

async function trim(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length <= max) return;
  for (const req of keys.slice(0, keys.length - max)) await cache.delete(req);
}

function isStatic(url) {
  return url.pathname.startsWith("/static/");
}
function isMedia(url) {
  return url.pathname.startsWith("/media/");
}
function bypass(url, request) {
  if (request.method !== "GET") return true;
  if (url.origin !== self.location.origin) return true;
  if (request.headers.has("range")) return true;                 // flux vidéo HLS
  if (url.pathname.startsWith("/admin/")) return true;           // back-office Django
  if (url.pathname.startsWith("/i18n/")) return true;            // bascule de langue
  if (url.pathname.startsWith("/tuteur/")) return true;          // API tuteur IA
  if (url.pathname.includes("/repondre/") || url.pathname.includes("/qcm/")) return true;
  if (url.pathname.endsWith(".m3u8") || url.pathname.endsWith(".ts")) return true;
  return false;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (bypass(url, request)) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstPage(request));
    return;
  }
  if (isStatic(url)) {
    event.respondWith(cacheFirst(request, PRECACHE));
    return;
  }
  if (isMedia(url)) {
    event.respondWith(staleWhileRevalidate(request, RUNTIME).then((r) => {
      trim(RUNTIME, MAX_MEDIA);
      return r;
    }));
    return;
  }
  event.respondWith(staleWhileRevalidate(request, RUNTIME));
});

async function networkFirstPage(request) {
  const cache = await caches.open(PAGES);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok && fresh.type === "basic") {
      cache.put(request, fresh.clone());
      trim(PAGES, MAX_PAGES);
    }
    return fresh;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const offline = await caches.match(OFFLINE_URL);
    return offline || new Response("Hors ligne", { status: 503, headers: { "Content-Type": "text/plain" } });
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (err) {
    return cached || Response.error();
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((fresh) => {
      if (fresh && fresh.ok) cache.put(request, fresh.clone());
      return fresh;
    })
    .catch(() => null);
  return cached || (await network) || Response.error();
}

/* Permet à la page de forcer l'activation d'une nouvelle version. */
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});
