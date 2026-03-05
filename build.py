#!/usr/bin/env python3
"""Fetch RSS feeds from NL news sources and generate a static HTML page."""

import json
import os
import shutil
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from jinja2 import Environment, FileSystemLoader


def load_sources(path="sources.json"):
    with open(path) as f:
        return json.load(f)


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

            articles.append({
                "title": entry.get("title", "Untitled"),
                "link": entry.get("link", "#"),
                "published": published,
                "source_name": source["name"],
                "source_slug": source["slug"],
            })

    articles.sort(key=lambda a: a["published"], reverse=True)
    return articles


def build_site(articles, sources):
    env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
    template = env.get_template("index.html")

    now = datetime.now(timezone.utc)
    html = template.render(articles=articles, sources=sources, updated=now)

    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w") as f:
        f.write(html)

    shutil.copy("static/style.css", "output/style.css")
    shutil.copytree("static/logos", "output/logos", dirs_exist_ok=True)
    print(f"Built output/index.html with {len(articles)} articles.")


def main():
    sources = load_sources()
    articles = fetch_articles(sources)
    build_site(articles, sources)


if __name__ == "__main__":
    main()
