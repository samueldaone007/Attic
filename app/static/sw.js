/* =====================================================================
   Attic - service worker (offline support)
   Strategy is "network first, cache fallback" for everything same-origin:
   - online you always get fresh content (edits show up immediately),
   - offline the app shell and your last view keep working,
   - /api/ requests fail with a 503 JSON instead of a crash.
   Bump the CACHE name to force every client to pick up new assets.
   ===================================================================== */
const CACHE = "attic-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll([
        "/offline",
        "/manifest.json",
        "/static/css/styles.css",
        "/static/js/ui.js",
        "/static/js/app.js",
        "/static/js/items.js",
        "/static/js/api.js",
        "/static/icons/favicon.svg",
        "/static/icons/icon.svg",
      ]))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function offlineJson() {
  return new Response(JSON.stringify({ detail: "You're offline." }), {
    status: 503,
    headers: { "Content-Type": "application/json" },
  });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // never touch external requests

  event.respondWith(
    fetch(request).then((response) => {
      // Cache successful GETs so they are available offline. Never cache
      // redirects (e.g. the login redirect) or error pages.
      if (response.status === 200) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    }).catch(() => {
      if (request.mode === "navigate") {
        return caches.match("/").then((hit) => hit || caches.match("/offline"));
      }
      if (url.pathname.startsWith("/api/")) {
        return offlineJson();
      }
      return caches.match(request);
    })
  );
});