var CACHE = 'goodfeed-v2';
// Relative to this file, because the site is served from a subpath on GitHub Pages.
var PRECACHE = ['./', 'search.html', 'style.css', 'manifest.json'];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.addAll(PRECACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);

  // Leave third-party requests (such as the weather API) to the browser.
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (e.request.destination === 'image') {
    // Logos and icons rarely change, so cached copies are used first.
    e.respondWith(
      caches.match(e.request).then(function(cached) {
        return cached || fetch(e.request).then(function(resp) {
          saveResponse(e, e.request, resp);
          return resp;
        });
      })
    );
    return;
  }

  // Pages, styles, and article data stay fresh, with the saved copy used offline.
  // Saving without the query string keeps one copy of search.html and style.css.
  var key = url.origin + url.pathname;
  e.respondWith(
    fetch(e.request).then(function(resp) {
      saveResponse(e, key, resp);
      return resp;
    }).catch(function() {
      return caches.match(key).then(function(cached) {
        if (cached) return cached;
        if (e.request.mode === 'navigate') return caches.match('./');
        return Response.error();
      });
    })
  );
});

function saveResponse(e, key, resp) {
  if (!resp.ok) return;
  var clone = resp.clone();
  e.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.put(key, clone);
    })
  );
}
