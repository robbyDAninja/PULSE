"""PyPI source collector — package download trends via pypistats API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from sources.base import Signal

logger = logging.getLogger("sources.pypi")

PYPI_STATS_API = "https://pypistats.org/api"
PYPI_API = "https://pypi.org/pypi"


def collect(
    topic_id: str,
    keywords: list[str],
    since: datetime,
    config: dict,
    topic_metadata: dict | None = None,
) -> list[Signal]:
    """
    Collect PyPI signals: recent download stats for packages matching keywords.

    Uses pypistats.org API for download counts and pypi.org for package metadata.
    Only tracks packages explicitly listed in topic metadata or config.
    """
    signals: list[Signal] = []

    # Get package names to track from topic metadata or config
    packages = []
    if topic_metadata and topic_metadata.get("pypi_packages"):
        packages = topic_metadata["pypi_packages"]
    if config.get("packages"):
        packages.extend(config["packages"])

    # Also search PyPI for keywords
    if config.get("search_enabled", True):
        for keyword in keywords[:3]:  # Limit to avoid rate limits
            try:
                found = _search_packages(keyword, limit=5)
                packages.extend(found)
            except Exception as e:
                logger.warning(f"  PyPI search failed for '{keyword}': {e}")

    # Deduplicate package names
    packages = list(set(p.lower() for p in packages))

    for package_name in packages:
        try:
            stats = _get_recent_downloads(package_name)
            if not stats:
                continue

            pkg_info = _get_package_info(package_name)
            version = pkg_info.get("version", "") if pkg_info else ""
            summary = pkg_info.get("summary", "") if pkg_info else ""

            signals.append(Signal(
                topic_id=topic_id,
                source_type="pypi",
                source_url=f"https://pypi.org/project/{package_name}/",
                title=f"PyPI: {package_name} ({version})" if version else f"PyPI: {package_name}",
                points_or_stars=stats.get("last_week", 0),
                discovered_at=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "package": package_name,
                    "version": version,
                    "summary": summary[:300],
                    "downloads_last_day": stats.get("last_day", 0),
                    "downloads_last_week": stats.get("last_week", 0),
                    "downloads_last_month": stats.get("last_month", 0),
                },
            ))
        except Exception as e:
            logger.warning(f"  PyPI stats failed for '{package_name}': {e}")

    logger.info(f"  pypi: {len(signals)} signals")
    return signals


def _search_packages(query: str, limit: int = 5) -> list[str]:
    """Search PyPI for packages matching query. Returns package names."""
    # PyPI doesn't have a great search API, use the simple search
    resp = httpx.get(
        f"https://pypi.org/search/",
        params={"q": query},
        timeout=15,
        follow_redirects=True,
    )
    resp.raise_for_status()

    # Parse package names from HTML (simple extraction)
    names = []
    for line in resp.text.split("\n"):
        if 'class="package-snippet__name"' in line:
            # Extract text between > and <
            start = line.rfind(">") + 1
            end = line.rfind("<", start)
            if start > 0 and end > start:
                name = line[start:end].strip()
                if name:
                    names.append(name)
            if len(names) >= limit:
                break
    return names


def _get_recent_downloads(package_name: str) -> dict | None:
    """Get recent download stats from pypistats.org."""
    resp = httpx.get(
        f"{PYPI_STATS_API}/packages/{package_name}/recent",
        timeout=10,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {})


def _get_package_info(package_name: str) -> dict | None:
    """Get package metadata from PyPI."""
    resp = httpx.get(
        f"{PYPI_API}/{package_name}/json",
        timeout=10,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    return data.get("info", {})
