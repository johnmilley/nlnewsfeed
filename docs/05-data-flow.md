# Data Flow: From RSS to Browser

This document traces how a news article travels from a publisher's RSS feed to appearing on the page.

---

## Step 1: RSS feeds

RSS (Really Simple Syndication) is an XML format that news sites publish for automated readers. Each source in `sources.json` has a `feed_url`:

```json
{ "name": "CBC NL", "slug": "cbc", "feed_url": "https://www.cbc.ca/webfeed/rss/rss-canada-newfoundland" }
```

An RSS feed looks something like this (simplified):

```xml
<rss>
  <channel>
    <item>
      <title>Premier announces new ferry route</title>
      <link>https://www.cbc.ca/news/...</link>
      <pubDate>Sat, 15 Mar 2026 18:16:42 GMT</pubDate>
      <description>The provincial government announced...</description>
    </item>
    <!-- more items... -->
  </channel>
</rss>
```

Most feeds contain only the 10-20 most recent articles. Once an article drops off the feed, it's gone — which is why we maintain an archive.

---

## Step 2: Fetching and parsing (Python)

`build.py` uses `requests` to download each feed and `feedparser` to parse the XML:

```python
resp = requests.get(source["feed_url"], timeout=15)
feed = feedparser.parse(resp.content)

for entry in feed.entries:
    # entry.title, entry.link, entry.published, entry.summary
```

Each entry is normalized into a consistent format:

```python
{
    "title": "Premier announces new ferry route",
    "link": "https://www.cbc.ca/news/...",
    "published": datetime(2026, 3, 15, 15, 46, 42, tzinfo=NDT),
    "source_name": "CBC NL",
    "source_slug": "cbc",
    "summary": "The provincial government announced..."
}
```

The `published` timestamp is converted from whatever timezone the source uses to Newfoundland time (NST/NDT).

---

## Step 3: Archive merge

Fresh articles are merged into the existing cache (`data/articles.json`):

```
Existing cache (170 articles)
         +
Fresh RSS articles (85 articles, many duplicates)
         =
Merged cache (175 articles — only 5 were truly new)
```

Deduplication is by URL — if an article's `link` already exists in the cache, the fresh copy is skipped. This means the original timestamp and data are preserved.

---

## Step 4: Serialization

Before saving, datetime objects are converted to ISO 8601 strings:

```
Python datetime:  datetime(2026, 3, 15, 15, 46, 42, tzinfo=NDT)
JSON string:      "2026-03-15T15:46:42-02:30"
```

The `-02:30` is Newfoundland Daylight Time (NDT). In winter, it would be `-03:30` (NST). The offset is preserved so the time can be accurately reconstructed later.

---

## Step 5: Template rendering

`build.py` filters to the last 7 days and passes articles to the Jinja2 template:

```python
cutoff = now - timedelta(days=7)
recent = [a for a in articles if a["published"] >= cutoff]
```

The template (`templates/index.html`) loops over articles:

```html
{% for article in articles %}
<article class="article-row" data-source="{{ article.source_slug }}">
  <time datetime="{{ article.published.isoformat() }}">
    {{ article.published.strftime('%b %-d') }}
    {{ article.published.strftime('%I:%M%p').lstrip('0').lower() }}
  </time>
  <img src="logos/{{ article.source_slug }}.png" alt="{{ article.source_name }}">
  <a href="{{ article.link }}">{{ article.title }}</a>
</article>
{% endfor %}
```

**Jinja2 syntax:**
- `{% for ... %}` — loop
- `{{ ... }}` — output a value
- `.strftime()` — Python date formatting (`%b` = "Mar", `%-d` = "15", `%I:%M%p` = "3:46pm")

The output is plain HTML — no JavaScript needed to display the articles.

---

## Step 6: In the browser

When a user visits the page, the HTML is already complete. JavaScript then adds interactivity:

```
HTML arrives (all articles visible)
  |
  v
JS reads localStorage for preferences
  |
  v
Applies theme (dark/light)
Marks visited links
Applies source filters
  |
  v
User sees their personalized view
```

The `data-source` attribute on each `<article>` element is what JavaScript uses for filtering:

```html
<article class="article-row" data-source="cbc">
```

```js
// Show only CBC articles
articles.forEach(function(article) {
  var show = article.getAttribute('data-source') === 'cbc';
  article.style.display = show ? '' : 'none';
});
```

---

## The full journey

```
CBC publishes article
        |
        v
RSS feed XML updates
        |
        v  (every 15 min)
build.py fetches feed
        |
        v
Parsed into Python dict
        |
        v
Merged into data/articles.json (deduped by URL)
        |
        v
Filtered to 7 days, rendered to HTML via Jinja2
        |
        v
Deployed to GitHub Pages
        |
        v  (user visits)
Browser loads HTML (articles already in page)
        |
        v
JavaScript adds filtering, themes, visited tracking
```
