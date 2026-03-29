"""Hugging Face source collector — trending models, spaces, and papers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from sources.base import Signal

logger = logging.getLogger("sources.huggingface")

HF_API_BASE = "https://huggingface.co/api"


def collect(
    topic_id: str,
    keywords: list[str],
    since: datetime,
    config: dict,
    topic_metadata: dict | None = None,
) -> list[Signal]:
    """
    Collect Hugging Face signals: trending models and spaces matching keywords.

    The HF API supports searching models and spaces by keyword.
    """
    signals: list[Signal] = []
    max_results = config.get("max_results", 10)

    for keyword in keywords:
        # Search models
        try:
            models = _search_models(keyword, max_results)
            for model in models:
                last_modified = model.get("lastModified", "")
                if last_modified and last_modified < since.isoformat():
                    continue

                model_id = model.get("id", "")
                downloads = model.get("downloads", 0)
                likes = model.get("likes", 0)

                signals.append(Signal(
                    topic_id=topic_id,
                    source_type="huggingface",
                    source_url=f"https://huggingface.co/{model_id}",
                    title=f"Model: {model_id}",
                    points_or_stars=likes,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "type": "model",
                        "downloads": downloads,
                        "likes": likes,
                        "pipeline_tag": model.get("pipeline_tag", ""),
                        "tags": model.get("tags", [])[:10],
                    },
                ))
        except Exception as e:
            logger.warning(f"  HF model search failed for '{keyword}': {e}")

        # Search spaces
        try:
            spaces = _search_spaces(keyword, max_results)
            for space in spaces:
                last_modified = space.get("lastModified", "")
                if last_modified and last_modified < since.isoformat():
                    continue

                space_id = space.get("id", "")
                likes = space.get("likes", 0)

                signals.append(Signal(
                    topic_id=topic_id,
                    source_type="huggingface",
                    source_url=f"https://huggingface.co/spaces/{space_id}",
                    title=f"Space: {space_id}",
                    points_or_stars=likes,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "type": "space",
                        "likes": likes,
                        "sdk": space.get("sdk", ""),
                    },
                ))
        except Exception as e:
            logger.warning(f"  HF space search failed for '{keyword}': {e}")

    logger.info(f"  huggingface: {len(signals)} signals")
    return signals


def _search_models(query: str, limit: int = 10) -> list[dict]:
    """Search HF models by keyword, sorted by downloads."""
    resp = httpx.get(
        f"{HF_API_BASE}/models",
        params={
            "search": query,
            "sort": "downloads",
            "direction": "-1",
            "limit": limit,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _search_spaces(query: str, limit: int = 10) -> list[dict]:
    """Search HF spaces by keyword, sorted by likes."""
    resp = httpx.get(
        f"{HF_API_BASE}/spaces",
        params={
            "search": query,
            "sort": "likes",
            "direction": "-1",
            "limit": limit,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
