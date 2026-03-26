"""Hacker News source collector — keyword search via HN Algolia API."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from sources.base import Signal

logger = logging.getLogger("sources.hackernews")


def collect(
    topic_id: str,
    keywords: list[str],
    since: datetime,
    config: dict,
    topic_metadata: dict | None = None,
) -> list[Signal]:
    """
    Collect Hacker News signals for a topic.

    For each keyword:
    1. Query Algolia search_by_date for stories with date filter
    2. Capture title, points, num_comments, URL
    3. Also query comment mentions (nbHits only) for frequency tracking

    Args:
        topic_id: The topic UUID.
        keywords: List of keyword variants for the topic.
        since: Only return stories created after this datetime (UTC).
        config: Source-specific config from config.yml.
        topic_metadata: Unused for HN, accepted for interface consistency.

    Returns:
        List of Signal objects. Never raises — logs errors internally.
    """
    base_url = config.get("base_url", "https://hn.algolia.com/api/v1")
    max_results = config.get("max_results_per_keyword", 50)
    min_points = config.get("min_points", 3)
    count_comments = config.get("count_comment_mentions", True)

    since_unix = int(since.timestamp())

    signals: list[Signal] = []
    seen_urls: set[str] = set()
    total_comment_mentions = 0

    for keyword in keywords:
        # --- Story search ---
        try:
            story_signals, comment_count = _search_keyword(
                base_url, keyword, since_unix, max_results, min_points,
                count_comments, topic_id,
            )
            for sig in story_signals:
                if sig.source_url not in seen_urls:
                    seen_urls.add(sig.source_url)
                    signals.append(sig)
            total_comment_mentions += comment_count
        except Exception as e:
            logger.error(f"HN search failed for keyword '{keyword}': {e}")

    if total_comment_mentions > 0:
        logger.info(f"  HN comment mentions (all keywords): {total_comment_mentions}")

    return signals


def _search_keyword(
    base_url: str,
    keyword: str,
    since_unix: int,
    max_results: int,
    min_points: int,
    count_comments: bool,
    topic_id: str,
) -> tuple[list[Signal], int]:
    """Search HN Algolia for a single keyword. Returns (signals, comment_mention_count)."""
    signals = []
    comment_mentions = 0

    with httpx.Client(timeout=15.0) as client:
        # --- Stories ---
        story_params = {
            "query": keyword,
            "tags": "story",
            "numericFilters": f"created_at_i>{since_unix}",
            "hitsPerPage": min(max_results, 50),
        }
        resp = client.get(f"{base_url}/search_by_date", params=story_params)
        resp.raise_for_status()
        data = resp.json()

        for hit in data.get("hits", []):
            points = hit.get("points") or 0
            if points < min_points:
                continue

            # Build the canonical HN URL
            hn_id = hit.get("objectID", "")
            story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
            hn_url = f"https://news.ycombinator.com/item?id={hn_id}"

            signals.append(Signal(
                topic_id=topic_id,
                source_type="hackernews",
                source_url=hn_url,
                title=hit.get("title", "Untitled"),
                points_or_stars=points,
                discovered_at=hit.get("created_at"),
                metadata={
                    "points": points,
                    "num_comments": hit.get("num_comments", 0),
                    "hn_id": hn_id,
                    "external_url": story_url if story_url != hn_url else None,
                    "author": hit.get("author"),
                },
            ))

        # --- Comment mention count (nbHits only) ---
        if count_comments:
            comment_params = {
                "query": keyword,
                "tags": "comment",
                "numericFilters": f"created_at_i>{since_unix}",
                "hitsPerPage": 0,  # We only need nbHits
            }
            comment_resp = client.get(
                f"{base_url}/search_by_date", params=comment_params
            )
            comment_resp.raise_for_status()
            comment_mentions = comment_resp.json().get("nbHits", 0)

    return signals, comment_mentions
