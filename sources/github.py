"""GitHub source collector — repo search and star counts via GitHub API."""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from sources.base import Signal

logger = logging.getLogger("sources.github")

API_BASE = "https://api.github.com"


def collect(
    topic_id: str,
    keywords: list[str],
    since: datetime,
    config: dict,
    topic_metadata: dict | None = None,
) -> list[Signal]:
    """
    Collect GitHub signals for a topic.

    1. Search repos by keywords (sort by stars, pushed since `since`)
    2. If topic has a primary_repo in metadata, fetch its star count directly

    Args:
        topic_id: The topic UUID.
        keywords: List of keyword variants for the topic.
        since: Only return repos pushed after this datetime (UTC).
        config: Source-specific config from config.yml.
        topic_metadata: Optional topic metadata (may contain primary_repo).

    Returns:
        List of Signal objects. Never raises — logs errors internally.
    """
    token = os.environ.get("GH_PAT", "")
    if not token:
        logger.warning("GH_PAT not set — GitHub collection will be unauthenticated (lower rate limits)")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": config.get("user_agent", "bridge-ninja-pulse/1.0"),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    max_results = config.get("max_results_per_keyword", 10)
    min_stars = config.get("min_stars", 5)
    since_str = since.strftime("%Y-%m-%d")

    signals: list[Signal] = []
    seen_urls: set[str] = set()

    # --- 1. Search repos by keyword ---
    for keyword in keywords:
        try:
            signals_for_kw = _search_repos(
                keyword, since_str, max_results, min_stars, headers, topic_id
            )
            for sig in signals_for_kw:
                if sig.source_url not in seen_urls:
                    seen_urls.add(sig.source_url)
                    signals.append(sig)
        except Exception as e:
            logger.error(f"GitHub search failed for keyword '{keyword}': {e}")

    # --- 2. Fetch primary repo star count if configured ---
    if topic_metadata and topic_metadata.get("primary_repo"):
        try:
            primary_signal = _fetch_repo(
                topic_metadata["primary_repo"], headers, topic_id
            )
            if primary_signal and primary_signal.source_url not in seen_urls:
                seen_urls.add(primary_signal.source_url)
                signals.append(primary_signal)
        except Exception as e:
            logger.error(f"GitHub primary repo fetch failed: {e}")

    return signals


def _search_repos(
    keyword: str,
    since_str: str,
    max_results: int,
    min_stars: int,
    headers: dict,
    topic_id: str,
) -> list[Signal]:
    """Search GitHub repos by keyword, return Signal list."""
    query = f"{keyword} pushed:>{since_str} stars:>={min_stars}"
    url = f"{API_BASE}/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(max_results, 30),
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    signals = []
    for repo in data.get("items", [])[:max_results]:
        signals.append(Signal(
            topic_id=topic_id,
            source_type="github",
            source_url=repo["html_url"],
            title=repo["full_name"],
            points_or_stars=repo.get("stargazers_count", 0),
            metadata={
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": repo.get("language"),
                "description": (repo.get("description") or "")[:300],
                "topics": repo.get("topics", []),
                "pushed_at": repo.get("pushed_at"),
            },
        ))

    return signals


def _fetch_repo(
    repo_full_name: str,
    headers: dict,
    topic_id: str,
) -> Signal | None:
    """Fetch a single repo by owner/name and return a Signal."""
    url = f"{API_BASE}/repos/{repo_full_name}"

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code == 404:
            logger.warning(f"Primary repo not found: {repo_full_name}")
            return None
        resp.raise_for_status()
        repo = resp.json()

    return Signal(
        topic_id=topic_id,
        source_type="github",
        source_url=repo["html_url"],
        title=repo["full_name"],
        points_or_stars=repo.get("stargazers_count", 0),
        metadata={
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language"),
            "description": (repo.get("description") or "")[:300],
            "topics": repo.get("topics", []),
            "pushed_at": repo.get("pushed_at"),
            "is_primary_repo": True,
        },
    )
