# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NL News Feed is a static site generator that aggregates RSS feeds from Newfoundland & Labrador news sources into a single HTML page. It runs on a 15-minute cron via GitHub Actions, deploying to GitHub Pages.

## Build & Run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python build.py
```

Output goes to `output/` (index.html, style.css, logos/). There are no tests.

## Architecture

**Single-script build** (`build.py`): Loads sources from `sources.json`, fetches RSS feeds with `feedparser`/`requests`, converts timestamps to Newfoundland time (NST/NDT with manual DST calculation), renders `templates/index.html` via Jinja2, and copies static assets to `output/`.

**Key data flow**: `sources.json` → fetch RSS → normalize articles (title, link, published, source_name, source_slug, summary) → sort by date descending → render template → static site in `output/`.

**Adding a news source**: Add an entry to `sources.json` with `name`, `slug`, and `feed_url`. Place a matching logo at `static/logos/<slug>.png`.

**Frontend** (`templates/index.html`): Self-contained — inline JS handles dark/light theme toggle (localStorage), visited link tracking (localStorage, capped at 500), and source filtering. CSS is in `static/style.css`. No build tooling or JS bundler.

**Deployment** (`.github/workflows/build.yml`): GitHub Actions builds every 15 min, uploads `output/` as a Pages artifact.
