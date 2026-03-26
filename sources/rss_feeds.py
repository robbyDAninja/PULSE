"""RSS source collector — Google Alerts, Google News, and configurable RSS feeds."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import feedparser
import httpx

from sources.base import Signal

logger = logging.getLogger("sources.rss_feeds")


def collect(
    topic_id: str,
    keywords: list[str],
    since: datetime,
    config: dict,
    topic_metadata: dict | None = None,
) -> list[Signal]:
    """
    Collect RSS/news signals for a topic.

    For each configured feed URL:
    1. Fetch and parse with feedparser
    2. Filter entries by date >= since
    3. Match against keywords in title + description (case-insensitive)

    Also builds a Google News RSS search URL per keyword for broader coverage.

    Args:
        topic_id: The topic UUID.
        keywords: List of keyword variants for the topic.
        since: Only return articles published after this datetime (UTC).
        config: Source-specific config from config.yml (expects feeds[] list).
        topic_metadata: Unused for RSS, accepted for interface consistency.

    Returns:
        List of Signal objects. Never raises — logs errors internally.
    """
    feeds = config.get("feeds", [])
    user_agent = config.get("user_agent", "bridge-ninja-pulse/1.0")

    signals: list[Signal] = []
    seen_urls: set[str] = set()

    # --- 1. Configured RSS feeds (Google Alerts, etc.) ---
    for feed_cfg in feeds:
        try:
            feed_signals = _fetch_feed(
                feed_url=feed_cfg["url"],
                feed_name=feed_cfg.get("name", "RSS"),
                keywords=keywords,
                since=since,
                user_agent=user_agent,
                topic_id=topic_id,
            )
            for sig in feed_signals:
                if sig.source_url not in seen_urls:
                    seen_urls.add(sig.source_url)
                    signals.append(sig)
        except Exception as e:
            logger.error(f"RSS feed '{feed_cfg.get('name', 'unknown')}' failed: {e}")

    # --- 2. Google News keyword search ---
    for keyword in keywords:
        try:
            gn_url = _build_google_news_url(keyword)
            gn_signals = _fetch_feed(
                feed_url=gn_url,
                feed_name=f"Google News: {keyword}",
                keywords=keywords,
                since=since,
                user_agent=user_agent,
                topic_id=topic_id,
                match_keywords=False,  # Already keyword-filtered by Google
            )
            for sig in gn_signals:
                if sig.source_url not in seen_urls:
                    seen_urls.add(sig.source_url)
                    signals.append(sig)
        except Exception as e:
            logger.error(f"Google News RSS failed for keyword '{keyword}': {e}")

    return signals


def _build_google_news_url(keyword: str) -> str:
    """Build a Google News RSS search URL for a keyword."""
    from urllib.parse import quote
    encoded = quote(keyword)
    return (
        f"https://news.google.com/rss/search"
        f"?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    )


def _fetch_feed(
    feed_url: str,
    feed_name: str,
    keywords: list[str],
    since: datetime,
    user_agent: str,
    topic_id: str,
    match_keywords: bool = True,
) -> list[Signal]:
    """Fetch a single RSS feed, filter by date and keywords, return Signals."""
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                feed_url,
                headers={"User-Agent": user_agent},
                follow_redirects=True,
            )
            resp.raise_for_status()
            raw_text = resp.text
    except httpx.HTTPError as e:
        logger.warning(f"  RSS fetch failed for '{feed_name}': {e}")
        return []

    feed = feedparser.parse(raw_text)
    if not feed.entries:
        return []

    signals = []
    keywords_lower = [kw.lower() for kw in keywords]

    for entry in feed.entries:
        # --- Date filter ---
        entry_date = _parse_entry_date(entry)
        if entry_date and entry_date < since:
            continue

        # --- Keyword match (if required) ---
        if match_keywords:
            title = (entry.get("title") or "").lower()
            description = (entry.get("summary") or entry.get("description") or "").lower()
            text = f"{title} {description}"
            if not any(kw in text for kw in keywords_lower):
                continue

        # --- Build signal ---
        link = entry.get("link", "")
        if not link:
            continue

        entry_title = entry.get("title", "Untitled")
        entry_desc = (entry.get("summary") or entry.get("description") or "")[:500]
        date_str = entry_date.isoformat() if entry_date else None

        signals.append(Signal(
            topic_id=topic_id,
            source_type="rss",
            source_url=link,
            title=entry_title,
            points_or_stars=None,  # RSS has no numeric score
            discovered_at=date_str,
            metadata={
                "source_name": feed_name,
                "description": entry_desc,
            },
        ))

    return signals


def _parse_entry_date(entry) -> datetime | None:
    """Extract a timezone-aware datetime from a feedparser entry."""
    for date_field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, date_field, None)
        if parsed:
            try:
                return datetime.fromtimestamp(
                    time.mktime(parsed), tz=timezone.utc
                )
            except (ValueError, OverflowError):
                continue
    return None
