/* Service Worker mínimo para Fidemar Cortex PWA.
 *
 * Estrategia:
 * - Estrategia network-first para assets estáticos (HTML/CSS/JS/iconos)
 *   con fallback al cache si la red falla → permite abrir la app aunque
 *   el server local esté momentáneamente offline.
 * - NO interceptamos `/api/*` — esto es crítico porque el chat usa SSE
 *   (Server-Sent Events) streaming. Un SW que cachea SSE rompe el stream.
 * - Cache versionado: al subir el version string se invalida todo.
 *
 * Para forzar un update en clientes activos:
 *   1. Subir CACHE_VERSION
 *   2. El SW nuevo se instala y reclama clientes (skipWaiting + clients.claim)
 *   3. La página se recarga en el próximo navigation o al cerrar/abrir
 */

// Bump esta versión cada vez que cambien static/index.html o assets críticos.
// Al cambiar, el browser instala un SW nuevo, activate() limpia los caches
// viejos y clients.claim() toma control inmediato sin requerir hard refresh.
const CACHE_VERSION = 'cortex-v140';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable.png',
  '/favicon.png',
];


self.addEventListener('install', (event) => {
  // Precachear los assets críticos para que la app abra aunque haya
  // problemas momentáneos de red.
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});


self.addEventListener('activate', (event) => {
  // Limpiar caches viejos de versiones anteriores
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});


self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // No interceptar nada que no sea GET (POST/PUT/DELETE pasan directo)
  if (req.method !== 'GET') return;

  // No interceptar APIs — especialmente /api/chat/stream que usa SSE.
  // Cualquier intermediación rompe el streaming chunked.
  if (url.pathname.startsWith('/api/')) return;

  // No interceptar la página de reset — su único propósito es desregistrar
  // este mismo SW. Si la intercepta y devuelve cache, nunca se ejecuta el
  // script de limpieza.
  if (url.pathname === '/reset-cache.html' || url.pathname === '/reset-cache') return;

  // No interceptar requests cross-origin (CDNs de React, fonts, etc.)
  if (url.origin !== location.origin) return;

  // Network-first para todo lo demás (assets estáticos)
  event.respondWith(
    fetch(req)
      .then((response) => {
        // Cachear sólo respuestas exitosas
        if (response && response.ok && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_VERSION).then((cache) => {
            cache.put(req, clone).catch(() => {});
          });
        }
        return response;
      })
      .catch(() => {
        // Si la red falla, intentar servir del cache
        return caches.match(req).then((cached) => {
          if (cached) return cached;
          // Sin cache: para navegaciones, fallback al index cacheado
          if (req.mode === 'navigate') {
            return caches.match('/');
          }
          // Sin nada útil: devolver un error mínimo
          return new Response('Offline y sin cache disponible.', {
            status: 503,
            statusText: 'Service Unavailable',
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
          });
        });
      })
  );
});


// Mensaje desde la página → permite forzar update programáticamente
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
