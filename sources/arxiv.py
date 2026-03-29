"""arXiv source collector — research papers via the arXiv API."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from sources.base import Signal

logger = logging.getLogger("sources.arxiv")

ARXIV_API = "http://export.arxiv.org/api/query"


def collect(
    topic_id: str,
    keywords: list[str],
    since: datetime,
    config: dict,
    topic_metadata: dict | None = None,
) -> list[Signal]:
    """
    Collect arXiv signals: recent papers matching keywords.

    Uses the arXiv API (Atom feed) to search for papers in cs.AI,
    cs.CL, cs.LG, and cs.MA categories.
    """
    signals: list[Signal] = []
    max_results = config.get("max_results", 10)
    categories = config.get("categories", "cs.AI+OR+cs.CL+OR+cs.LG+OR+cs.MA")

    for keyword in keywords:
        try:
            papers = _search_papers(keyword, categories, max_results)
            for paper in papers:
                published = paper.get("published", "")
                if published:
                    try:
                        pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                        if pub_dt < since:
                            continue
                    except ValueError:
                        pass

                signals.append(Signal(
                    topic_id=topic_id,
                    source_type="arxiv",
                    source_url=paper.get("link", ""),
                    title=paper.get("title", "Untitled"),
                    points_or_stars=None,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "authors": paper.get("authors", [])[:5],
                        "summary": paper.get("summary", "")[:500],
                        "categories": paper.get("categories", []),
                        "published": published,
                    },
                ))
        except Exception as e:
            logger.warning(f"  arXiv search failed for '{keyword}': {e}")

    logger.info(f"  arxiv: {len(signals)} signals")
    return signals


def _search_papers(query: str, categories: str, max_results: int) -> list[dict]:
    """Search arXiv for papers matching query in given categories."""
    search_query = f"all:{query}+AND+cat:{categories}"
    resp = httpx.get(
        ARXIV_API,
        params={
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return _parse_atom_feed(resp.text)


def _parse_atom_feed(xml_text: str) -> list[dict]:
    """Parse arXiv Atom feed into list of paper dicts."""
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(xml_text)
    papers = []

    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else "Untitled"

        summary_el = entry.find("atom:summary", ns)
        summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else ""

        published_el = entry.find("atom:published", ns)
        published = published_el.text if published_el is not None and published_el.text else ""

        # Get the abstract link (HTML page)
        link = ""
        for link_el in entry.findall("atom:link", ns):
            if link_el.get("type") == "text/html":
                link = link_el.get("href", "")
                break
        if not link:
            id_el = entry.find("atom:id", ns)
            link = id_el.text if id_el is not None and id_el.text else ""

        authors = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text)

        categories = []
        for cat_el in entry.findall("arxiv:primary_category", ns):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)
        for cat_el in entry.findall("atom:category", ns):
            term = cat_el.get("term", "")
            if term and term not in categories:
                categories.append(term)

        papers.append({
            "title": title,
            "summary": summary,
            "published": published,
            "link": link,
            "authors": authors,
            "categories": categories,
        })

    return papers
