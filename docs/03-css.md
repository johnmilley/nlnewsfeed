# CSS Concepts

The site's styles are in `static/style.css`. This document walks through the key CSS concepts used.

---

## 1. CSS custom properties (variables)

```css
:root {
  --bg: #ffffff;
  --text: #111111;
  --link: #111111;
  --border: #dddddd;
  /* ... */
}

[data-theme="dark"] {
  --bg: #111111;
  --text: #e0e0e0;
  --link: #e0e0e0;
  --border: #333333;
}
```

Custom properties (prefixed with `--`) are defined on `:root` (the `<html>` element) and used throughout the stylesheet with `var()`:

```css
body {
  background: var(--bg);
  color: var(--text);
}
```

**Why this matters:** Instead of finding and changing every color value for dark mode, we just redefine the variables. The same `var(--bg)` reference automatically picks up the new value when `data-theme="dark"` is set on `<html>`.

---

## 2. Dark mode: three layers

The CSS handles dark mode with three selectors, in priority order:

```css
/* 1. Default (light) */
:root { --bg: #ffffff; }

/* 2. Explicit dark (user clicked the toggle) */
[data-theme="dark"] { --bg: #111111; }

/* 3. OS preference (user hasn't chosen, but their OS is in dark mode) */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #111111; }
}
```

The `:not([data-theme="light"])` selector means: "apply dark mode from OS preference, but only if the user hasn't explicitly chosen light mode." This gives manual choice priority over automatic detection.

---

## 3. Flexbox layout

The article rows use flexbox to align the timestamp, logo, and title in a single line:

```css
.article-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
```

- `display: flex` — makes child elements flow in a row
- `align-items: center` — vertically centers items
- `gap: 0.6rem` — spacing between items (cleaner than using margins)

The timestamp and logo use `flex-shrink: 0` so they stay at their natural size while the title takes up remaining space.

---

## 4. Responsive design with `@media`

```css
@media (max-width: 600px) {
  .article-row {
    font-size: 0.9rem;
    gap: 0.4rem;
  }
  .article-time {
    min-width: 5.5rem;
    font-size: 0.7rem;
  }
}
```

`@media (max-width: 600px)` means "apply these styles only when the screen is 600px wide or less" (phones). The site reduces font sizes, padding, and spacing to fit smaller screens.

---

## 5. Accessibility: skip link

```css
.skip-link {
  position: absolute;
  top: -100%;
}
.skip-link:focus {
  top: 0;
}
```

This link is invisible until a keyboard user presses Tab. It then appears at the top of the page and lets them jump directly to the feed, skipping the header and filters. This is a standard accessibility pattern.

---

## 6. Attribute selectors for state

```css
.filter-btn[aria-pressed="true"] {
  opacity: 1;
  font-weight: 600;
  border-color: var(--text);
}
.filter-btn[aria-pressed="false"] {
  opacity: 0.4;
}
```

Instead of toggling CSS classes, the filter buttons use `aria-pressed` — an accessibility attribute that already tracks whether a button is active. The CSS reads that attribute directly with `[aria-pressed="true"]`. This avoids maintaining separate "visual state" and "accessibility state."

---

## 7. Box model reset

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
```

- Removes default browser margins/padding from all elements (which vary between browsers)
- `box-sizing: border-box` makes `width` include padding and borders, which is more intuitive than the default (`content-box`)

---

## 8. Units used

| Unit | Used for | Meaning |
|------|----------|---------|
| `rem` | Font sizes, padding, gaps | Relative to the root font size (usually 16px) |
| `px` | Logo dimensions, borders | Exact pixel values |
| `%` | Skip link positioning | Relative to parent |
| `vw` | Settings panel width on mobile | Viewport (screen) width |
