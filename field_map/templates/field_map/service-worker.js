{% load static %}
const CACHE_NAME = "openskagit-field-v1";
const PRECACHE_URLS = [
  "{% url 'field_map:manifest' %}",
  "{% static 'field_map/field_map.css' %}",
  "{% static 'field_map/field_map.js' %}",
  "{% static 'field_map/icons/field-map-icon.svg' %}",
  "{% static 'field_map/vendor/leaflet/leaflet.css' %}",
  "{% static 'field_map/vendor/leaflet/leaflet.js' %}",
  "{% static 'field_map/vendor/leaflet/images/layers.png' %}",
  "{% static 'field_map/vendor/leaflet/images/layers-2x.png' %}",
  "{% static 'field_map/vendor/leaflet/images/marker-icon.png' %}",
  "{% static 'field_map/vendor/leaflet/images/marker-icon-2x.png' %}",
  "{% static 'field_map/vendor/leaflet/images/marker-shadow.png' %}"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key.startsWith("openskagit-field-") && key !== CACHE_NAME)
        .map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/field/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => new Response(
        "<!doctype html><meta name='viewport' content='width=device-width'><title>Parcel Field Map</title><style>body{font:16px system-ui;padding:2rem;background:#d9e3df;color:#173f3a}main{max-width:28rem;margin:auto;background:white;padding:1.5rem;border-radius:1rem}</style><main><h1>You are offline</h1><p>Reconnect to load the private parcel map and current ownership records.</p></main>",
        { headers: { "Content-Type": "text/html; charset=utf-8" } }
      ))
    );
    return;
  }

  if (url.pathname.startsWith("/static/field_map/") || url.pathname === "{% url 'field_map:manifest' %}") {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      }))
    );
  }
});
