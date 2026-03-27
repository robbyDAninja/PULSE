"""Base types and interface for signal collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Signal:
    """A single signal event from any source."""

    topic_id: str
    source_type: str  # "github", "hackernews", "youtube", "rss"
    source_url: str  # Unique URL (dedup key with topic_id + source_type)
    title: str
    points_or_stars: Optional[int] = None
    discovered_at: Optional[str] = None  # ISO timestamp
    metadata: dict = field(default_factory=dict)

    def to_db_row(self) -> dict:
        """Convert to a dict suitable for Supabase upsert."""
        return {
            "topic_id": self.topic_id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "title": self.title,
            "points_or_stars": self.points_or_stars,
            "metadata": self.metadata,
            "discovered_at": self.discovered_at or datetime.now(timezone.utc).isoformat(),
        }
