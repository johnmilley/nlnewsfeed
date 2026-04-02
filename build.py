#!/usr/bin/env python3
"""Fetch RSS feeds from NL news sources and generate a static HTML page."""

import html
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup
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


def _fetch_release_time(url):
    """Fetch the datePublished from a single gov.nl.ca release page."""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "NLNewsFeed/1.0"})
        resp.raise_for_status()
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', resp.text)
        if match:
            return datetime.fromisoformat(match.group(1))
    except Exception:
        pass
    return None


def scrape_gov_releases(source, cached_links):
    """Scrape government news releases from gov.nl.ca. Skip already-cached links."""
    articles = []
    resp = requests.get(source["scrape_url"], timeout=15, headers={
        "User-Agent": "NLNewsFeed/1.0"
    })
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    current_date = None
    for el in soup.select(".entry-content h2, .entry-content ul li"):
        if el.name == "h2":
            current_date = el.get_text(strip=True)
            continue
        if current_date is None:
            continue
        a_tag = el.select_one("span.title a")
        dept_span = el.select_one("span.department")
        if not a_tag:
            continue
        link = a_tag.get("href", "")
        if not link.startswith("http"):
            link = "https://www.gov.nl.ca" + link
        if link in cached_links:
            continue

        # Fetch actual publish time from individual release page
        pub = _fetch_release_time(link)
        if pub is None:
            year_match = re.search(r"/releases/(\d{4})/", link)
            year = int(year_match.group(1)) if year_match else datetime.now().year
            try:
                pub = datetime.strptime(f"{current_date} {year}", "%B %d %Y")
            except ValueError:
                pub = datetime.now()
            pub = pub.replace(hour=12, tzinfo=NST)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        department = dept_span.get_text(strip=True) if dept_span else ""
        articles.append({
            "title": a_tag.get_text(strip=True),
            "link": link,
            "published": to_nl_time(pub),
            "source_name": source["name"],
            "source_slug": source["slug"],
            "summary": department,
        })
    return articles


def fetch_stjohns_news(source):
    """Fetch news from St. John's JSON API."""
    articles = []
    resp = requests.get(source["api_url"], timeout=15, headers={
        "User-Agent": "NLNewsFeed/1.0"
    })
    resp.raise_for_status()
    for item in resp.json():
        title = html.unescape(item.get("title", "Untitled"))
        link = item.get("link", "#")
        # Parse date and time: "Thursday, April 2, 2026" + "02:00:18 PM"
        date_str = item.get("postedDate", "")
        time_str = item.get("postedTime", "12:00:00 PM")
        try:
            pub = datetime.strptime(f"{date_str} {time_str}", "%A, %B %d, %Y %I:%M:%S %p")
            pub = pub.replace(tzinfo=NST)
        except ValueError:
            pub = datetime.now(timezone.utc)
        summary = item.get("description", "")
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        summary = html.unescape(summary)
        summary = summary[:200].rsplit(" ", 1)[0] if len(summary) > 200 else summary
        articles.append({
            "title": title,
            "link": link,
            "published": to_nl_time(pub),
            "source_name": source["name"],
            "source_slug": source["slug"],
            "summary": summary,
        })
    return articles


def fetch_articles(sources, cached_links=None):
    cached_links = cached_links or set()
    articles = []
    for source in sources:
        print(f"Fetching {source['name']}...")
        if source.get("scrape_url"):
            try:
                articles.extend(scrape_gov_releases(source, cached_links))
            except Exception as e:
                print(f"  Error scraping {source['name']}: {e}")
            continue
        if source.get("api_url"):
            try:
                articles.extend(fetch_stjohns_news(source))
            except Exception as e:
                print(f"  Error fetching {source['name']}: {e}")
            continue
        if not source.get("feed_url"):
            continue
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
            summary = html.unescape(summary)
            summary = summary[:200].rsplit(" ", 1)[0] if len(summary) > 200 else summary

            link = entry.get("link", "")
            if not link or not link.startswith("http"):
                # Podcast feeds often lack <link>; use enclosure URL instead
                enclosures = entry.get("enclosures", [])
                if enclosures:
                    link = enclosures[0].get("href", "#")
                else:
                    link = "#"
            # If link points to a media file, use source_url as a landing page
            if link.endswith((".mp3", ".m4a", ".wav")) and source.get("source_url"):
                link = source["source_url"]

            articles.append({
                "title": entry.get("title", "Untitled"),
                "link": link,
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


def _dedup_key(article):
    """Return a dedup key: (title, published, source_slug) for shared-link sources, else link."""
    pub = article["published"]
    if isinstance(pub, datetime):
        pub = pub.isoformat()
    return (article["title"], pub, article["source_slug"])


def merge_articles(cached, fresh):
    """Merge fresh articles into cached, deduplicating by content."""
    seen = {_dedup_key(a) for a in cached}
    merged = list(cached)
    new_count = 0
    for article in fresh:
        key = _dedup_key(article)
        if key not in seen:
            seen.add(key)
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

    # Only show last 7 calendar days on the main page (today + 6 previous days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today_start - timedelta(days=6)
    recent = [a for a in articles if a["published"] >= cutoff]
    recent.sort(key=lambda a: a["published"], reverse=True)

    # Group articles by date for display
    from itertools import groupby as itertools_groupby
    articles_by_date = []
    for date_key, group in itertools_groupby(recent, key=lambda a: a["published"].strftime("%A, %B %-d")):
        articles_by_date.append((date_key, list(group)))

    today_label = now.strftime("%A, %B %-d")

    html = template.render(articles_by_date=articles_by_date, sources=sources, updated=now, css_hash=css_hash, today_label=today_label)

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

    # Fetch fresh articles from RSS (pass cached links so scrapers skip known entries)
    cached_links = {a["link"] for a in cached}
    fresh = fetch_articles(sources, cached_links)

    # Merge fresh into cache (dedup by URL)
    all_articles = merge_articles(cached, fresh)

    # Save the full archive back to cache
    save_cache(serialize_articles(all_articles))

    # Build the site (7-day view)
    build_site(all_articles, sources)


if __name__ == "__main__":
    main()
