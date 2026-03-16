#!/usr/bin/env python3
"""Fetch RSS feeds from NL news sources and generate a static HTML page."""

import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from jinja2 import Environment, FileSystemLoader


def load_sources(path="sources.json"):
    with open(path) as f:
        return json.load(f)


NST = timezone(timedelta(hours=-3, minutes=-30))
NDT = timezone(timedelta(hours=-2, minutes=-30))


def to_nl_time(dt):
    """Convert a datetime to Newfoundland time (NST/NDT)."""
    utc_dt = dt.astimezone(timezone.utc)
    year = utc_dt.year
    # NDT: second Sunday in March 2:00 AM to first Sunday in November 2:00 AM
    mar1 = datetime(year, 3, 1, tzinfo=timezone.utc)
    spring = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    spring = spring.replace(hour=2)
    nov1 = datetime(year, 11, 1, tzinfo=timezone.utc)
    fall = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    fall = fall.replace(hour=2)
    if spring <= utc_dt < fall:
        return utc_dt.astimezone(NDT)
    return utc_dt.astimezone(NST)


def fetch_articles(sources):
    articles = []
    for source in sources:
        print(f"Fetching {source['name']}...")
        try:
            resp = requests.get(source["feed_url"], timeout=15, headers={
                "User-Agent": "NLNewsFeed/1.0"
            })
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            print(f"  Error fetching {source['name']}: {e}")
            continue

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published"):
                try:
                    published = parsedate_to_datetime(entry.published)
                except Exception:
                    pass
            if published is None and hasattr(entry, "updated"):
                try:
                    published = parsedate_to_datetime(entry.updated)
                except Exception:
                    pass
            if published is None:
                published = datetime.now(timezone.utc)

            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)

            summary = entry.get("summary", entry.get("description", ""))
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            summary = summary[:200].rsplit(" ", 1)[0] if len(summary) > 200 else summary

            articles.append({
                "title": entry.get("title", "Untitled"),
                "link": entry.get("link", "#"),
                "published": to_nl_time(published),
                "source_name": source["name"],
                "source_slug": source["slug"],
                "summary": summary,
            })

    articles.sort(key=lambda a: a["published"], reverse=True)
    return articles


CACHE_PATH = "data/articles.json"


def load_cache():
    """Load the article cache from disk."""
    if not os.path.exists(CACHE_PATH):
        return []
    with open(CACHE_PATH) as f:
        return json.load(f)


def save_cache(articles):
    """Save the article cache to disk."""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(articles, f, indent=2, default=str)
    print(f"Saved {len(articles)} articles to cache.")


def merge_articles(cached, fresh):
    """Merge fresh articles into cached, deduplicating by link URL."""
    seen = {a["link"] for a in cached}
    merged = list(cached)
    new_count = 0
    for article in fresh:
        if article["link"] not in seen:
            seen.add(article["link"])
            merged.append(article)
            new_count += 1
    print(f"Merged {new_count} new articles ({len(merged)} total).")
    return merged


def serialize_articles(articles):
    """Convert articles to JSON-serializable format."""
    serialized = []
    for a in articles:
        serialized.append({
            "title": a["title"],
            "link": a["link"],
            "published": a["published"].isoformat() if isinstance(a["published"], datetime) else a["published"],
            "source_name": a["source_name"],
            "source_slug": a["source_slug"],
            "summary": a["summary"],
        })
    return serialized


def deserialize_articles(raw):
    """Convert cached JSON articles back to usable dicts with datetime objects."""
    articles = []
    for a in raw:
        pub = a["published"]
        if isinstance(pub, str):
            pub = datetime.fromisoformat(pub)
        articles.append({
            "title": a["title"],
            "link": a["link"],
            "published": pub,
            "source_name": a["source_name"],
            "source_slug": a["source_slug"],
            "summary": a.get("summary", ""),
        })
    return articles


def build_site(articles, sources):
    env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
    template = env.get_template("index.html")

    now = to_nl_time(datetime.now(timezone.utc))

    # Cache-busting hash from CSS file content
    import hashlib
    with open("static/style.css", "rb") as f:
        css_hash = hashlib.md5(f.read()).hexdigest()[:8]

    # Only show last 7 days on the main page
    cutoff = now - timedelta(days=7)
    recent = [a for a in articles if a["published"] >= cutoff]
    recent.sort(key=lambda a: a["published"], reverse=True)

    html = template.render(articles=recent, sources=sources, updated=now, css_hash=css_hash)

    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w") as f:
        f.write(html)

    # Render search page
    search_template = env.get_template("search.html")
    search_html = search_template.render(sources=sources, css_hash=css_hash)
    with open("output/search.html", "w") as f:
        f.write(search_html)

    # Split archive into per-year JSON files for search page
    # Clean out stale data files first
    data_dir = "output/data"
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    os.makedirs(data_dir)
    by_year = {}
    for a in articles:
        pub = a["published"]
        if isinstance(pub, str):
            y = int(pub[:4])
        else:
            y = pub.year
        by_year.setdefault(y, []).append(a)

    years_index = []
    for y in sorted(by_year.keys(), reverse=True):
        year_articles = serialize_articles(by_year[y]) if isinstance(by_year[y][0]["published"], datetime) else by_year[y]
        with open(f"output/data/{y}.json", "w") as f:
            json.dump(year_articles, f, default=str)
        years_index.append({"year": y, "count": len(year_articles)})

    with open("output/data/years.json", "w") as f:
        json.dump(years_index, f)
    print(f"Split archive into {len(years_index)} year files: {', '.join(str(y['year']) for y in years_index)}")

    shutil.copy("static/style.css", "output/style.css")
    shutil.copy("static/manifest.json", "output/manifest.json")
    shutil.copy("static/sw.js", "output/sw.js")
    shutil.copytree("static/logos", "output/logos", dirs_exist_ok=True)
    shutil.copytree("static/icons", "output/icons", dirs_exist_ok=True)
    print(f"Built output/index.html with {len(recent)} articles (7-day view).")


def main():
    sources = load_sources()

    # Load existing cache
    cached_raw = load_cache()
    cached = deserialize_articles(cached_raw)

    # Fetch fresh articles from RSS
    fresh = fetch_articles(sources)

    # Merge fresh into cache (dedup by URL)
    all_articles = merge_articles(cached, fresh)

    # Save the full archive back to cache
    save_cache(serialize_articles(all_articles))

    # Build the site (7-day view)
    build_site(all_articles, sources)


if __name__ == "__main__":
    main()
