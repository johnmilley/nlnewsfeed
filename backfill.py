#!/usr/bin/env python3
"""Backfill historical articles from sitemaps and Wayback Machine snapshots."""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

CACHE_PATH = "data/articles.json"
HEADERS = {"User-Agent": "NLNewsFeed-Backfill/1.0"}
REQUEST_DELAY = 0.5  # seconds between requests to be polite

NST = timezone(timedelta(hours=-3, minutes=-30))
NDT = timezone(timedelta(hours=-2, minutes=-30))


def to_nl_time(dt):
    utc_dt = dt.astimezone(timezone.utc)
    year = utc_dt.year
    mar1 = datetime(year, 3, 1, tzinfo=timezone.utc)
    spring = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    spring = spring.replace(hour=2)
    nov1 = datetime(year, 11, 1, tzinfo=timezone.utc)
    fall = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    fall = fall.replace(hour=2)
    if spring <= utc_dt < fall:
        return utc_dt.astimezone(NDT)
    return utc_dt.astimezone(NST)


def load_cache():
    if not os.path.exists(CACHE_PATH):
        return []
    with open(CACHE_PATH) as f:
        return json.load(f)


def save_cache(articles):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(articles, f, indent=2, default=str)


def merge_into_cache(new_articles):
    cached = load_cache()
    seen = {a["link"] for a in cached}
    added = 0
    for a in new_articles:
        if a["link"] not in seen:
            seen.add(a["link"])
            cached.append(a)
            added += 1
    cached.sort(key=lambda a: a["published"], reverse=True)
    save_cache(cached)
    return added, len(cached)


# ---------- Sitemap-based backfill ----------

def fetch_sitemap_index(url):
    """Fetch a sitemap index and return list of sitemap URLs."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text for loc in root.findall(".//s:sitemap/s:loc", ns)]


def fetch_sitemap_urls(url):
    """Fetch a sitemap and return list of (url, lastmod) tuples."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for url_el in root.findall(".//s:url", ns):
        loc = url_el.find("s:loc", ns)
        lastmod = url_el.find("s:lastmod", ns)
        if loc is not None:
            lm = lastmod.text if lastmod is not None else None
            urls.append((loc.text, lm))
    return urls


def scrape_title_from_page(url):
    """Fetch a page and extract the <title> or og:title."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Try og:title first
        match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if match:
            return match.group(1).strip()

        # Try <title> tag
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        if match:
            title = match.group(1).strip()
            # Strip site name suffix like " - VOCM" or " | NTV"
            title = re.split(r"\s*[|\-–—]\s*(?:VOCM|NTV|CBC|SaltWire|The Independent|Shoreline)", title)[0]
            return title.strip()
    except Exception:
        pass
    return None


def scrape_description_from_page(url, html=None):
    """Extract meta description or og:description from a page."""
    if html is None:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return ""

    match = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
    if match:
        return match.group(1).strip()[:200]
    match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    if match:
        return match.group(1).strip()[:200]
    return ""


def scrape_page_meta(url):
    """Fetch a page and extract title, description, and publish date."""
    import html as html_mod
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text

        title = None
        match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if match:
            title = match.group(1).strip()
        if not title:
            match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
            if match:
                title = match.group(1).strip()
                title = re.split(r"\s*[|\-–—]\s*(?:VOCM|NTV|CBC|SaltWire|The Independent|Shoreline)", title)[0].strip()

        # Decode HTML entities in title
        if title:
            title = html_mod.unescape(title)

        summary = scrape_description_from_page(url, html)

        # Extract real publication date from page metadata
        pub_date = None
        # Try article:published_time (Open Graph)
        match = re.search(r'<meta\s+property="article:published_time"\s+content="([^"]+)"', html)
        if match:
            pub_date = parse_lastmod(match.group(1))
        # Try datePublished in JSON-LD
        if not pub_date:
            match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
            if match:
                pub_date = parse_lastmod(match.group(1))
        # Try <time> with datetime attribute (common in WordPress)
        if not pub_date:
            match = re.search(r'<time[^>]+datetime="([^"]+)"[^>]*class="[^"]*entry-date', html)
            if not match:
                match = re.search(r'<time[^>]+class="[^"]*entry-date[^"]*"[^>]+datetime="([^"]+)"', html)
            if match:
                pub_date = parse_lastmod(match.group(1))

        return title, summary, pub_date
    except Exception:
        return None, "", None


def parse_lastmod(lastmod_str):
    """Parse a sitemap lastmod date string into a datetime."""
    if not lastmod_str:
        return None
    lastmod_str = lastmod_str.strip()
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(lastmod_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Try fromisoformat as fallback
    try:
        dt = datetime.fromisoformat(lastmod_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def backfill_from_sitemap(source_name, source_slug, sitemap_url,
                          url_filter=None, year_filter=None, limit=None):
    """Backfill articles from a sitemap or sitemap index."""
    print(f"\n=== Backfilling {source_name} from sitemap ===")
    print(f"Sitemap: {sitemap_url}")

    # Check if it's a sitemap index or a flat sitemap
    resp = requests.get(sitemap_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    content = resp.text

    all_urls = []

    if "<sitemapindex" in content:
        root = ET.fromstring(resp.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_locs = [loc.text for loc in root.findall(".//s:sitemap/s:loc", ns)]

        # Filter to post sitemaps if possible
        post_sitemaps = [s for s in sitemap_locs if "post" in s.lower()]
        if not post_sitemaps:
            post_sitemaps = sitemap_locs

        print(f"Found {len(post_sitemaps)} post sitemaps")

        for i, sm_url in enumerate(post_sitemaps):
            print(f"  Fetching sitemap {i+1}/{len(post_sitemaps)}: {sm_url}")
            try:
                urls = fetch_sitemap_urls(sm_url)
                all_urls.extend(urls)
                time.sleep(REQUEST_DELAY)
            except Exception as e:
                print(f"    Error: {e}")
    else:
        all_urls = fetch_sitemap_urls(sitemap_url)

    print(f"Found {len(all_urls)} URLs total")

    # Apply URL filter (e.g., only article paths)
    if url_filter:
        all_urls = [(u, lm) for u, lm in all_urls if url_filter(u)]
        print(f"After URL filter: {len(all_urls)}")

    # Apply year filter
    if year_filter:
        filtered = []
        for u, lm in all_urls:
            dt = parse_lastmod(lm)
            if dt and dt.year in year_filter:
                filtered.append((u, lm))
            elif not dt:
                filtered.append((u, lm))  # keep if no date to filter on
        all_urls = filtered
        print(f"After year filter ({year_filter}): {len(all_urls)}")

    # Deduplicate against existing cache
    cached = load_cache()
    existing_links = {a["link"] for a in cached}
    new_urls = [(u, lm) for u, lm in all_urls if u not in existing_links]
    print(f"After dedup: {len(new_urls)} new URLs to fetch")

    if limit:
        new_urls = new_urls[:limit]
        print(f"Limited to {limit} URLs")

    # Scrape each page for title and summary
    articles = []
    for i, (url, lastmod) in enumerate(new_urls):
        if (i + 1) % 25 == 0 or i == 0:
            print(f"  Scraping {i+1}/{len(new_urls)}: {url[:80]}...")

        title, summary, page_date = scrape_page_meta(url)
        if not title:
            continue

        # Prefer the page's own publish date over sitemap lastmod
        pub_dt = page_date or (parse_lastmod(lastmod) if lastmod else None)
        if pub_dt is None:
            pub_dt = datetime.now(timezone.utc)

        articles.append({
            "title": title,
            "link": url,
            "published": to_nl_time(pub_dt).isoformat(),
            "source_name": source_name,
            "source_slug": source_slug,
            "summary": summary,
        })

        time.sleep(REQUEST_DELAY)

    # Merge into cache
    if articles:
        added, total = merge_into_cache(articles)
        print(f"\nAdded {added} new articles ({total} total in cache)")
    else:
        print("\nNo new articles to add")

    return len(articles)


# ---------- Wayback Machine backfill ----------

def backfill_from_wayback(source_name, source_slug, feed_url, year_filter=None):
    """Backfill articles from Wayback Machine snapshots of an RSS feed."""
    print(f"\n=== Backfilling {source_name} from Wayback Machine ===")
    print(f"Feed: {feed_url}")

    # Get list of all snapshots
    cdx_url = (
        f"https://web.archive.org/cdx/search/cdx"
        f"?url={feed_url}&output=json&fl=timestamp,statuscode&filter=statuscode:200"
    )
    resp = requests.get(cdx_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    rows = json.loads(resp.text)

    if len(rows) <= 1:
        print("No snapshots found")
        return 0

    timestamps = [row[0] for row in rows[1:]]  # skip header row

    if year_filter:
        timestamps = [t for t in timestamps if int(t[:4]) in year_filter]

    # Sample snapshots (one per week to avoid redundancy)
    sampled = []
    last_week = None
    for ts in timestamps:
        week = ts[:8]  # YYYYMMDD granularity; use YYYYWW for weekly
        year_week = f"{ts[:4]}-{datetime.strptime(ts[:8], '%Y%m%d').isocalendar()[1]:02d}"
        if year_week != last_week:
            sampled.append(ts)
            last_week = year_week

    print(f"Found {len(timestamps)} snapshots, sampled {len(sampled)} (one per week)")

    import feedparser

    cached = load_cache()
    existing_links = {a["link"] for a in cached}
    all_articles = []

    for i, ts in enumerate(sampled):
        wb_url = f"https://web.archive.org/web/{ts}id_/{feed_url}"
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  Fetching snapshot {i+1}/{len(sampled)}: {ts}")

        try:
            resp = requests.get(wb_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in existing_links:
                    continue

                # Parse publication date
                pub_dt = None
                for date_field in ["published", "updated"]:
                    raw = getattr(entry, date_field, None)
                    if raw:
                        try:
                            from email.utils import parsedate_to_datetime
                            pub_dt = parsedate_to_datetime(raw)
                            break
                        except Exception:
                            pass
                if pub_dt is None:
                    # Use snapshot timestamp as fallback
                    pub_dt = datetime.strptime(ts[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)

                summary = entry.get("summary", entry.get("description", ""))
                summary = re.sub(r"<[^>]+>", "", summary).strip()[:200]

                existing_links.add(link)
                all_articles.append({
                    "title": entry.get("title", "Untitled"),
                    "link": link,
                    "published": to_nl_time(pub_dt).isoformat(),
                    "source_name": source_name,
                    "source_slug": source_slug,
                    "summary": summary,
                })

        except Exception as e:
            print(f"    Error: {e}")

        time.sleep(REQUEST_DELAY)

    if all_articles:
        added, total = merge_into_cache(all_articles)
        print(f"\nAdded {added} new articles ({total} total in cache)")
    else:
        print("\nNo new articles to add")

    return len(all_articles)


# ---------- Source configs ----------

SOURCES = {
    "vocm": {
        "name": "VOCM",
        "slug": "vocm",
        "sitemap": "https://vocm.com/sitemap.xml",
        "feed_url": "https://vocm.com/feed/",
        "url_filter": lambda u: re.match(r"https://vocm\.com/\d{4}/", u) is not None,
    },
    "ntv": {
        "name": "NTV",
        "slug": "ntv",
        "sitemap": "https://ntv.ca/sitemap.xml",
        "feed_url": "https://ntv.ca/feed/",
        "url_filter": None,
    },
    "independent": {
        "name": "The Independent",
        "slug": "independent",
        "sitemap": "https://theindependent.ca/sitemap.xml",
        "feed_url": "https://theindependent.ca/feed/",
        "url_filter": None,
    },
    "cbc": {
        "name": "CBC NL",
        "slug": "cbc",
        "feed_url": "https://www.cbc.ca/webfeed/rss/rss-canada-newfoundland",
        # No sitemap — Wayback only
    },
    "saltwire": {
        "name": "SaltWire",
        "slug": "saltwire",
        "feed_url": "https://www.saltwire.com/category/newfoundland-labrador/feed.xml",
        # Rolling sitemap only — Wayback is sparse
    },
    "shoreline": {
        "name": "Shoreline News",
        "slug": "shoreline",
        "feed_url": "https://theshoreline.ca/feed/",
        # Minimal archives
    },
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill historical articles")
    parser.add_argument("source", nargs="?", help="Source slug (vocm, ntv, independent, cbc, saltwire, shoreline) or 'all'")
    parser.add_argument("--year", type=int, nargs="+", help="Filter to specific years (e.g., --year 2024 2025)")
    parser.add_argument("--limit", type=int, help="Max articles to fetch per source")
    parser.add_argument("--method", choices=["sitemap", "wayback", "auto"], default="auto",
                        help="Backfill method (default: auto)")
    parser.add_argument("--list", action="store_true", help="List available sources")
    args = parser.parse_args()

    if args.list:
        print("Available sources:")
        for slug, cfg in SOURCES.items():
            methods = []
            if "sitemap" in cfg:
                methods.append("sitemap")
            if "feed_url" in cfg:
                methods.append("wayback")
            print(f"  {slug:15s} {cfg['name']:20s} methods: {', '.join(methods)}")
        return

    if not args.source:
        parser.print_help()
        return

    slugs = list(SOURCES.keys()) if args.source == "all" else [args.source]
    year_filter = set(args.year) if args.year else None

    for slug in slugs:
        if slug not in SOURCES:
            print(f"Unknown source: {slug}")
            continue

        cfg = SOURCES[slug]
        method = args.method

        if method == "auto":
            if "sitemap" in cfg:
                method = "sitemap"
            else:
                method = "wayback"

        if method == "sitemap":
            if "sitemap" not in cfg:
                print(f"{cfg['name']}: no sitemap available, falling back to wayback")
                method = "wayback"
            else:
                backfill_from_sitemap(
                    cfg["name"], cfg["slug"], cfg["sitemap"],
                    url_filter=cfg.get("url_filter"),
                    year_filter=year_filter,
                    limit=args.limit,
                )

        if method == "wayback":
            backfill_from_wayback(
                cfg["name"], cfg["slug"], cfg["feed_url"],
                year_filter=year_filter,
            )


if __name__ == "__main__":
    main()
