# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NL News Feed ("A Good Feed of NL News") is a static site generator that aggregates RSS
feeds and a few scraped/API sources from Newfoundland & Labrador news outlets into a
single HTML page. It runs on a 15-minute cron via GitHub Actions and deploys to GitHub
Pages. It is also an installable PWA (manifest + service worker) with offline support.

## Build & Run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python build.py
```

Output goes to `output/`: `index.html`, `search.html`, `style.css`, `manifest.json`,
`sw.js`, `logos/`, `icons/`, and `data/` (per-year archive JSON + `years.json`).
There are no tests.

## Architecture

**Single-script build** (`build.py`):
1. Loads sources from `sources.json`.
2. Loads the article archive from `data/articles.json` (the running cache, committed to the repo).
3. Fetches fresh items: RSS via `feedparser`/`requests`; `scrape_url` sources are HTML-scraped
   with BeautifulSoup (GovNL releases); `api_url` sources use a JSON endpoint (City of St. John's).
4. Normalizes each article to `title, link, published, source_name, source_slug, summary`.
5. Converts timestamps to Newfoundland time (NST/NDT via manual DST calculation in `to_nl_time`).
6. Merges fresh into the archive, deduping by `(title, published, source_slug)` (see `_dedup_key`).
7. Writes the full archive back to `data/articles.json`.
8. Renders `templates/index.html` (last 7 calendar days, grouped by date) and
   `templates/search.html` via Jinja2.
9. Splits the full archive into `output/data/<year>.json` files consumed by the search page.
10. Copies static assets to `output/`.

**Backfill** (`backfill.py`): one-off / manual tool to seed the archive with historical
articles from site sitemaps and Wayback Machine snapshots. Not run by CI. `python backfill.py --list`.

**Adding a news source**: add an entry to `sources.json` with `name`, `slug`, `feed_url`
(or `scrape_url` / `api_url` for the special cases), and a `type`
(`news`, `blog`, `podcast`, `government`, `institution`, `municipal`). Place a matching
logo at `static/logos/<slug>.png`. `type` drives grouping in the source picker; only
`news` sources are enabled by default in the UI.

**Frontend** (`templates/index.html`, `templates/search.html`): self-contained — inline JS
handles dark/light theme toggle (localStorage), visited-link tracking (localStorage, capped
at 500), per-source filtering + "minimal mode", a weather strip (open-meteo API, localStorage
city list), NL clock, auto-refresh on return after 15 min, and service-worker registration.
CSS is in `static/style.css` (grayscale palette, CSS custom properties, `?v=<md5>` cache-bust).
No build tooling or JS bundler.

**Service worker** (`static/sw.js`): network-first for navigations, cache-first for assets.

**Deployment** (`.github/workflows/build.yml`): GitHub Actions builds every 15 min, commits
the updated `data/articles.json` back to `main`, and uploads `output/` as a Pages artifact.
