"""Supabase client wrapper — thin layer over supabase-py for the intelligence schema."""
from __future__ import annotations

import logging
import os

from supabase import create_client, Client

logger = logging.getLogger("db")


def get_client() -> Client:
    """Create Supabase client from environment variables.

    Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.
    Uses service role key to bypass RLS.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def get_active_topics(client: Client) -> list[dict]:
    """Fetch all active topics from intelligence.topics."""
    return (
        client.schema("intelligence")
        .table("topics")
        .select("id, name, slug, keywords, current_stage, category, metadata")
        .eq("active", True)
        .execute()
        .data
    )


def upsert_signals(client: Client, signals: list[dict]) -> int:
    """Batch upsert signals into intelligence.signals.

    Deduplicates on (topic_id, source_type, source_url).
    Returns count of upserted rows.
    """
    if not signals:
        return 0
    response = (
        client.schema("intelligence")
        .table("signals")
        .upsert(signals, on_conflict="topic_id,source_type,source_url")
        .execute()
    )
    return len(response.data)


def upsert_snapshot(client: Client, snapshot: dict) -> dict:
    """Upsert a single snapshot row into intelligence.snapshots.

    Deduplicates on (topic_id, snapshot_date).
    Returns the upserted row.
    """
    response = (
        client.schema("intelligence")
        .table("snapshots")
        .upsert(snapshot, on_conflict="topic_id,snapshot_date")
        .execute()
    )
    return response.data[0] if response.data else snapshot


def get_latest_snapshot(client: Client, topic_id: str) -> dict | None:
    """Get the most recent snapshot for a topic (for delta calculation and hysteresis)."""
    response = (
        client.schema("intelligence")
        .table("snapshots")
        .select("*")
        .eq("topic_id", topic_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def insert_stage_transition(
    client: Client,
    topic_id: str,
    from_stage: str,
    to_stage: str,
    snapshot_id: str | None = None,
    notes: str = "",
) -> dict:
    """Record a stage transition in intelligence.stage_transitions."""
    row = {
        "topic_id": topic_id,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "notes": notes,
    }
    if snapshot_id:
        row["trigger_snapshot_id"] = snapshot_id
    return (
        client.schema("intelligence")
        .table("stage_transitions")
        .insert(row)
        .execute()
        .data[0]
    )


def update_topic_stage(client: Client, topic_id: str, stage: str) -> None:
    """Update the current_stage column on intelligence.topics."""
    (
        client.schema("intelligence")
        .table("topics")
        .update({"current_stage": stage})
        .eq("id", topic_id)
        .execute()
    )
