# JavaScript Walkthrough

All JavaScript in this project lives in two places:

- **Inline `<script>` in `templates/index.html`** — the main application logic
- **`static/sw.js`** — the service worker (covered in [04-service-worker.md](04-service-worker.md))

There is no build toolchain, no bundler, no npm. Just plain JavaScript that runs directly in the browser. Every concept below maps to something you'd see in an intro JS course.

---

## 1. Preventing flash of unstyled content (FOUC)

```html
<script>
  (function() {
    var theme = localStorage.getItem('theme');
    if (theme) document.documentElement.setAttribute('data-theme', theme);
    if (localStorage.getItem('minimal') === 'true')
      document.documentElement.classList.add('minimal');
  })();
</script>
```

This small script is in the `<head>`, before the page renders. It runs immediately.

**Concepts demonstrated:**
- **IIFE** (Immediately Invoked Function Expression) — `(function() { ... })()` runs the function right away and keeps variables out of the global scope
- **`localStorage`** — browser storage that persists between visits (key-value pairs, strings only)
- **`document.documentElement`** — refers to the `<html>` element
- **`setAttribute`** and **`classList`** — two ways to modify an element's attributes/classes

**Why it's in the `<head>`:** If we waited until the end of `<body>`, the page would flash in light mode before switching to dark. By reading the user's preference *before* the browser paints, we avoid that flicker.

---

## 2. Settings panel (open/close)

```js
var settingsToggle = document.getElementById('settings-toggle');
var settingsPanel = document.getElementById('settings-panel');
var settingsBackdrop = document.getElementById('settings-backdrop');

function openSettings() {
  settingsPanel.hidden = false;
  settingsBackdrop.hidden = false;
  settingsToggle.setAttribute('aria-expanded', 'true');
  settingsPanel.focus();
}

function closeSettings() {
  settingsPanel.hidden = true;
  settingsBackdrop.hidden = true;
  settingsToggle.setAttribute('aria-expanded', 'false');
  settingsToggle.focus();
}

settingsToggle.addEventListener('click', function() {
  if (settingsPanel.hidden) openSettings(); else closeSettings();
});

settingsBackdrop.addEventListener('click', closeSettings);

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && !settingsPanel.hidden) closeSettings();
});
```

**Concepts demonstrated:**
- **`document.getElementById()`** — selecting a single element by its `id`
- **`addEventListener()`** — attaching a function to run when an event occurs
- **The `hidden` property** — a built-in boolean that shows/hides elements (simpler than toggling CSS `display`)
- **Event types** — `'click'` for mouse/tap, `'keydown'` for keyboard
- **`aria-expanded`** — an accessibility attribute that tells screen readers whether a panel is open

**Pattern: backdrop click to close.** The backdrop is an invisible full-screen element behind the panel. Clicking anywhere outside the panel hits the backdrop, which triggers `closeSettings()`.

---

## 3. Dark mode toggle

```js
var darkCheckbox = document.getElementById('setting-dark');

function isDark() {
  var t = root.getAttribute('data-theme');
  return t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

darkCheckbox.checked = isDark();

darkCheckbox.addEventListener('change', function() {
  var next = darkCheckbox.checked ? 'dark' : 'light';
  root.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
});
```

**Concepts demonstrated:**
- **`window.matchMedia()`** — queries the user's OS-level preferences (here, dark mode)
- **Ternary operator** — `condition ? valueIfTrue : valueIfFalse`
- **`localStorage.setItem()`** — saving a preference so it persists across visits
- **`change` event** — fires when a checkbox or select value changes

**How the theme actually switches:** Setting `data-theme="dark"` on the `<html>` element activates different CSS custom property values (see [03-css.md](03-css.md)). The JavaScript doesn't change any colors directly — it just flips a switch that CSS responds to.

---

## 4. Visited link tracking

```js
var visited = JSON.parse(localStorage.getItem('visited') || '[]');
var visitedSet = new Set(visited);

document.querySelectorAll('.article-title a').forEach(function(a) {
  if (visitedSet.has(a.href)) a.classList.add('visited');
  a.addEventListener('click', function() {
    if (!visitedSet.has(a.href)) {
      visitedSet.add(a.href);
      visited.push(a.href);
      if (visited.length > 500) visited = visited.slice(-500);
      localStorage.setItem('visited', JSON.stringify(visited));
    }
    a.classList.add('visited');
  });
});
```

**Concepts demonstrated:**
- **`JSON.parse()` / `JSON.stringify()`** — converting between JavaScript objects and strings (localStorage only stores strings)
- **`Set`** — a collection of unique values with fast `.has()` lookups (O(1) vs O(n) for array `.indexOf()`)
- **`querySelectorAll()`** — selecting multiple elements with a CSS selector, returns a NodeList
- **`.forEach()`** — iterating over each element in a list
- **`classList.add()`** — adding a CSS class to an element
- **Array `.slice(-500)`** — keeping only the last 500 entries to prevent localStorage from growing forever

**Why not use the browser's built-in `:visited` CSS?** Browsers intentionally limit what `:visited` can style (for privacy — it could be used to detect which sites you've visited). It also doesn't persist across devices or distinguish between "visited from this feed" vs "visited from somewhere else." Using localStorage gives us full control.

---

## 5. Source filtering

```js
var buttons = document.querySelectorAll('.filter-btn');
var articles = document.querySelectorAll('.article-row');
var viewMode = 'all';

function applyFilters() {
  articles.forEach(function(article) {
    var src = article.getAttribute('data-source');
    var show = viewMode === 'all' ? isEnabled(src) : src === viewMode;
    article.style.display = show ? '' : 'none';
  });
  // ...button state updates...
}

buttons.forEach(function(btn) {
  btn.addEventListener('click', function() {
    var src = btn.getAttribute('data-source');
    if (src === viewMode || src === 'all') {
      viewMode = 'all';
    } else {
      viewMode = src;
    }
    applyFilters();
  });
});
```

**Concepts demonstrated:**
- **`data-*` attributes** — custom HTML attributes for storing data on elements (`data-source="cbc"`)
- **`getAttribute()`** — reading a `data-*` or any other attribute
- **`element.style.display`** — directly setting CSS properties from JavaScript
- **State management** — `viewMode` is a simple variable that tracks which filter is active. Clicking a button updates the variable, then `applyFilters()` re-reads it and updates the DOM.

**Pattern: single source of truth.** Instead of each button toggling articles independently (which gets tangled fast), there's one `viewMode` variable and one `applyFilters()` function that makes the page match the state. This is the same idea behind frameworks like React, just done manually.

---

## 6. Settings checkboxes and localStorage

```js
var sourceToggles = document.querySelectorAll('.source-toggle');
sourceToggles.forEach(function(cb) {
  var slug = cb.getAttribute('data-slug');
  cb.checked = enabledSources.indexOf(slug) !== -1;
  cb.addEventListener('change', function() {
    var enabled = [];
    sourceToggles.forEach(function(c) {
      if (c.checked) enabled.push(c.getAttribute('data-slug'));
    });
    enabledSources = enabled;
    localStorage.setItem('enabledSources', JSON.stringify(enabled));
    applyFilters();
  });
});
```

**Concepts demonstrated:**
- **`.checked`** — boolean property on checkbox inputs
- **`.indexOf() !== -1`** — checking if a value exists in an array (before `Set` and `.includes()` were common)
- **Building arrays with `.push()`** — iterating over checkboxes and collecting the checked ones
- **Syncing UI ↔ state ↔ storage** — checkbox changes update the `enabledSources` array, save to localStorage, and re-run `applyFilters()`

---

## Patterns worth noting

### No frameworks
This entire app uses zero libraries on the frontend. Everything is vanilla JavaScript and DOM APIs. This is intentional — for a project this size, a framework would add complexity without benefit.

### Everything in one IIFE
All the JavaScript is wrapped in a single `(function() { ... })()`. This prevents any variables from leaking into the global scope, which could conflict with other scripts.

### Progressive enhancement
The HTML page works without JavaScript — all articles are rendered server-side by Python. JavaScript adds interactivity (filtering, theming, visited tracking) on top. If JS fails to load, users still see the news.
