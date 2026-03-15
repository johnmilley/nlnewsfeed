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


def build_site(articles, sources):
    env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
    template = env.get_template("index.html")

    now = to_nl_time(datetime.now(timezone.utc))
    html = template.render(articles=articles, sources=sources, updated=now)

    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w") as f:
        f.write(html)

    shutil.copy("static/style.css", "output/style.css")
    shutil.copy("static/manifest.json", "output/manifest.json")
    shutil.copy("static/sw.js", "output/sw.js")
    shutil.copytree("static/logos", "output/logos", dirs_exist_ok=True)
    shutil.copytree("static/icons", "output/icons", dirs_exist_ok=True)
    print(f"Built output/index.html with {len(articles)} articles.")


def main():
    sources = load_sources()
    articles = fetch_articles(sources)
    build_site(articles, sources)


if __name__ == "__main__":
    main()
