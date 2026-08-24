const CACHE_NAME = "structurebase-v8";
const APP_SHELL = [
  "/offline",
  "/static/images/logo-mark.svg",
  "/static/images/logo-mark.webp",
  "/static/images/apple-touch-icon.png",
  "/static/images/icon-192.png",
  "/static/images/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const requestUrl = new URL(event.request.url);

  if (requestUrl.origin !== self.location.origin) {
    return;
  }

  const bypassedPrefixes = ["/dashboard", "/login", "/partner", "/staff", "/healthz"];
  if (bypassedPrefixes.some((prefix) => requestUrl.pathname.startsWith(prefix))) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match(event.request).then((cached) => cached || caches.match("/offline")))
    );
    return;
  }

  const isStaticBundle =
    requestUrl.pathname.startsWith("/static/") &&
    [".css", ".js", ".webmanifest"].some((suffix) => requestUrl.pathname.endsWith(suffix));

  if (isStaticBundle) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type !== "basic") {
            return response;
          }
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => {
          if (event.request.destination === "image") {
            return caches.match("/static/images/logo-mark.webp");
          }
          return Response.error();
        });
    })
  );
});
