"""Base types and interface for signal collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    """A single signal event from any source."""

    topic_id: str
    source_type: str  # "github", "hackernews", "youtube", "rss"
    source_url: str  # Unique URL (dedup key with topic_id + source_type)
    title: str
    points_or_stars: Optional[int] = None
    discovered_at: Optional[str] = None  # ISO timestamp; defaults to now() on insert
    metadata: dict = field(default_factory=dict)
    # metadata examples:
    #   github:      {"stars": 1200, "forks": 45, "language": "Python"}
    #   hackernews:  {"points": 342, "num_comments": 87, "hn_id": "12345678"}
    #   rss:         {"source_name": "Google Alerts", "description": "..."}

    def to_db_row(self) -> dict:
        """Convert to a dict suitable for Supabase upsert."""
        row = {
            "topic_id": self.topic_id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "title": self.title,
            "points_or_stars": self.points_or_stars,
            "metadata": self.metadata,
        }
        if self.discovered_at:
            row["discovered_at"] = self.discovered_at
        return row
