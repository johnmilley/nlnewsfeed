# Architecture Overview

Good Feed: NL News is a **static site** — there is no server running when users visit it. A Python script runs every 15 minutes, fetches news from RSS feeds, generates plain HTML, and publishes it to GitHub Pages.

## How the pieces fit together

```
sources.json          List of news outlets and their RSS feed URLs
     |
     v
build.py              Python script that:
     |                  1. Loads sources.json
     |                  2. Fetches each RSS feed
     |                  3. Merges new articles into data/articles.json (the archive)
     |                  4. Renders the last 7 days into HTML using a template
     |
     v
templates/index.html  Jinja2 template — HTML structure + inline JavaScript
static/style.css      All styling (CSS custom properties, dark mode, responsive)
static/sw.js          Service worker for offline support (PWA)
static/manifest.json  PWA manifest (app name, icons)
     |
     v
output/               The final site (uploaded to GitHub Pages)
  index.html           Rendered HTML with all articles baked in
  style.css            Copied from static/
  data/articles.json   Full article archive (for future search page)
  logos/               Source logos
```

## Key concept: static site generation

Unlike a traditional web app where a server processes each request, this site is **pre-built**. The Python script runs *before* any user visits. By the time someone opens the page, everything is already plain HTML — no database queries, no API calls, no server-side code running.

This is the same approach used by tools like Jekyll, Hugo, and Eleventy.

## The build cycle

This runs automatically via GitHub Actions (`.github/workflows/build.yml`):

1. **Checkout** the repository
2. **Install** Python dependencies (`feedparser`, `requests`, `jinja2`)
3. **Run** `python build.py`
4. **Commit** the updated article cache (`data/articles.json`) back to the repo
5. **Deploy** the `output/` folder to GitHub Pages

The cron schedule `*/15 * * * *` means "every 15 minutes."

## File-by-file summary

| File | Language | Purpose |
|------|----------|---------|
| `sources.json` | JSON | Configuration — which news sources to fetch |
| `build.py` | Python | Fetches RSS, manages the article archive, generates HTML |
| `data/articles.json` | JSON | Persistent archive of all articles ever fetched |
| `templates/index.html` | HTML + Jinja2 + JS | Page structure, inline JavaScript for interactivity |
| `static/style.css` | CSS | All visual styling |
| `static/sw.js` | JavaScript | Service worker for offline/PWA support |
| `static/manifest.json` | JSON | PWA configuration (app name, icons) |
| `.github/workflows/build.yml` | YAML | GitHub Actions automation |

## What runs where

| Code | Runs on... | When |
|------|-----------|------|
| `build.py` | GitHub's servers (Actions) | Every 15 minutes |
| `templates/index.html` (Jinja2 parts) | GitHub's servers (during build) | Every 15 minutes |
| Inline `<script>` in index.html | User's browser | Every page visit |
| `sw.js` | User's browser (background) | After first visit |
| `style.css` | User's browser | Every page visit |
