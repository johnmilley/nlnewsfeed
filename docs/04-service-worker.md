# Service Worker & PWA

The file `static/sw.js` is a **service worker** — a JavaScript file that runs in the background, separate from the web page. It intercepts network requests and can serve cached responses, enabling offline support.

Combined with `static/manifest.json`, this makes the site a **Progressive Web App (PWA)** — users can "install" it to their home screen and use it like a native app.

---

## How the service worker is registered

In `templates/index.html`, at the bottom:

```js
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}
```

The `if` check ensures it only runs in browsers that support service workers. Registration tells the browser to download and install `sw.js`.

---

## The three lifecycle events

### 1. `install` — first time setup

```js
var CACHE = 'goodfeed-v1';
var PRECACHE = ['/', '/style.css'];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.addAll(PRECACHE);
    })
  );
  self.skipWaiting();
});
```

- Opens a named cache (`'goodfeed-v1'`)
- Downloads and stores the homepage and stylesheet
- `self.skipWaiting()` activates immediately instead of waiting for all tabs to close

**`e.waitUntil()`** tells the browser "don't finish installing until this async operation completes." Without it, the browser might consider installation done before caching finishes.

### 2. `activate` — cleanup old caches

```js
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
```

When the cache name changes (e.g., from `'goodfeed-v1'` to `'goodfeed-v2'`), this deletes all old caches. `self.clients.claim()` makes the new service worker take control of all open tabs immediately.

**Concepts:** `Promise.all()` runs multiple async operations in parallel and waits for all to complete. `.filter()` and `.map()` are array methods chained together — filter to the old caches, then map each one to a delete operation.

### 3. `fetch` — intercepting requests

```js
self.addEventListener('fetch', function(e) {
  if (e.request.mode === 'navigate') {
    // HTML pages: network-first
    e.respondWith(
      fetch(e.request).then(function(resp) {
        var clone = resp.clone();
        caches.open(CACHE).then(function(cache) { cache.put(e.request, clone); });
        return resp;
      }).catch(function() {
        return caches.match(e.request);
      })
    );
  } else {
    // Assets (CSS, images): cache-first
    e.respondWith(
      caches.match(e.request).then(function(cached) {
        return cached || fetch(e.request).then(function(resp) {
          var clone = resp.clone();
          caches.open(CACHE).then(function(cache) { cache.put(e.request, clone); });
          return resp;
        });
      })
    );
  }
});
```

Two strategies based on what's being requested:

**Network-first (HTML pages):** Try the network. If it works, cache the response and return it. If the network fails (offline), fall back to the cached version. This ensures users always get fresh news when online.

**Cache-first (CSS, images, etc.):** Check the cache first. If found, return it immediately (fast!). If not cached, fetch from the network and cache it for next time. Assets change rarely, so caching them is safe.

**Why `resp.clone()`?** A response body can only be read once. Since we need to both cache it *and* return it to the page, we clone it — one copy for the cache, one for the browser.

---

## The PWA manifest

`static/manifest.json` tells the browser how to behave when the site is "installed":

```json
{
  "name": "Good Feed: NL News",
  "short_name": "Good Feed",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#111111",
  "icons": [...]
}
```

- `display: "standalone"` — hides the browser's address bar, making it look like a native app
- `theme_color` — colors the status bar on mobile
- `icons` — used on the home screen; `"purpose": "maskable"` variants adapt to different icon shapes across devices

---

## Key takeaway

Service workers are powerful but conceptually simple: they sit between your page and the network, and you write rules for how to handle each request. The Cache API gives you a programmatic way to store and retrieve responses — think of it as `localStorage` but for full HTTP responses instead of just strings.
