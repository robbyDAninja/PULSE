#!/usr/bin/env python3
"""
Discovery Layer Generator — Bridge Ninja Intelligence Platform.

Reads the latest snapshots and stage transitions from Supabase,
builds a JSON payload for the combined email (Discovery Layer +
Deep Pulse). Runs Monday alongside generate_pulse.py.

Usage:
    export SUPABASE_URL=https://...
    export SUPABASE_SERVICE_ROLE_KEY=...
    python generate_discovery.py [--output discovery_payload.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_discovery")


def format_delta(delta: float | None) -> dict:
    """Format score delta into symbol, class, and display value."""
    if delta is None or delta == 0:
        return {"symbol": "—", "css_class": "stable", "value": "—"}
    if delta >= 5:
        return {"symbol": "▲", "css_class": "up", "value": f"▲{delta:.0f}"}
    if delta <= -5:
        return {"symbol": "▼", "css_class": "down", "value": f"▼{abs(delta):.0f}"}
    return {"symbol": "—", "css_class": "stable", "value": "—"}


def format_stage(stage: str) -> dict:
    """Format stage into display name and CSS class."""
    stages = {
        "emergence": {"label": "Emergence", "css_class": "stage-emergence"},
        "traction": {"label": "Traction", "css_class": "stage-traction"},
        "inflection": {"label": "Inflection", "css_class": "stage-inflection"},
    }
    return stages.get(stage, {"label": stage.title(), "css_class": "stage-emergence"})


def build_signal_summary(snapshot: dict) -> str:
    """Build a one-line summary of what drove the score."""
    parts = []
    hn = snapshot.get("hn_mentions") or 0
    if hn > 0:
        parts.append(f"{hn} HN mention{'s' if hn != 1 else ''}")
    gh = snapshot.get("github_stars") or 0
    if gh > 0:
        parts.append(f"{gh:,} GH stars")
    news = snapshot.get("news_mention_count") or 0
    if news > 0:
        parts.append(f"{news} news mention{'s' if news != 1 else ''}")
    yt = snapshot.get("youtube_video_count") or 0
    if yt > 0:
        parts.append(f"{yt} YT video{'s' if yt != 1 else ''}")
    return ", ".join(parts) if parts else "No signals this period"


def get_latest_snapshots(client) -> list[dict]:
    """Get the most recent snapshot for each active topic."""
    # Get the latest snapshot_date
    latest = (
        client.schema("intelligence")
        .table("snapshots")
        .select("snapshot_date")
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not latest:
        return []

    snapshot_date = latest[0]["snapshot_date"]
    logger.info(f"Latest snapshot date: {snapshot_date}")

    # Get all snapshots for that date with topic info
    snapshots = (
        client.schema("intelligence")
        .table("snapshots")
        .select("*, topics!inner(name, slug, category, first_seen, active)")
        .eq("snapshot_date", snapshot_date)
        .order("composite_score", desc=True)
        .execute()
        .data
    )
    return snapshots


def get_recent_transitions(client, days: int = 7) -> list[dict]:
    """Get stage transitions from the last N days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    transitions = (
        client.schema("intelligence")
        .table("stage_transitions")
        .select("*, topics!inner(name, slug)")
        .gte("transitioned_at", since)
        .order("transitioned_at", desc=True)
        .execute()
        .data
    )
    return transitions


def build_discovery_payload(snapshots: list[dict], transitions: list[dict]) -> dict:
    """Build the Discovery Layer JSON payload for the email edge function."""
    # Format transitions
    formatted_transitions = []
    for t in transitions:
        topic_name = t.get("topics", {}).get("name", "Unknown")
        from_stage = format_stage(t["from_stage"])
        to_stage = format_stage(t["to_stage"])
        direction = "▲" if _stage_rank(t["to_stage"]) > _stage_rank(t["from_stage"]) else "▼"
        formatted_transitions.append({
            "topic_name": topic_name,
            "from_stage": from_stage["label"],
            "to_stage": to_stage["label"],
            "direction": direction,
            "date": t["transitioned_at"][:10],
        })

    # Format topic list
    formatted_topics = []
    for i, s in enumerate(snapshots, 1):
        topic = s.get("topics", {})
        if not topic.get("active", True):
            continue
        delta = format_delta(float(s["score_delta"]) if s.get("score_delta") else None)
        stage = format_stage(s.get("stage", "emergence"))
        score = float(s["composite_score"]) if s.get("composite_score") else 0

        formatted_topics.append({
            "rank": i,
            "name": topic.get("name", "Unknown"),
            "slug": topic.get("slug", ""),
            "score": round(score),
            "delta": delta,
            "stage": stage,
            "summary": build_signal_summary(s),
            "category": topic.get("category", ""),
        })

    return {
        "transitions": formatted_transitions,
        "topics": formatted_topics,
        "snapshot_date": snapshots[0]["snapshot_date"] if snapshots else None,
        "topic_count": len(formatted_topics),
    }


def _stage_rank(stage: str) -> int:
    """Numeric rank for stage comparison."""
    return {"emergence": 1, "traction": 2, "inflection": 3}.get(stage, 0)


def main():
    parser = argparse.ArgumentParser(description="Generate Discovery Layer payload")
    parser.add_argument(
        "--output", "-o",
        default="discovery_payload.json",
        help="Output JSON file (default: discovery_payload.json)",
    )
    args = parser.parse_args()

    try:
        client = db.get_client()
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        sys.exit(1)

    logger.info("=== Discovery Layer Generation ===")

    snapshots = get_latest_snapshots(client)
    if not snapshots:
        logger.warning("No snapshots found. Skipping Discovery Layer.")
        # Write empty payload so downstream doesn't break
        Path(args.output).write_text(json.dumps({"discovery_layer": None}))
        return

    transitions = get_recent_transitions(client)
    logger.info(f"Found {len(snapshots)} snapshots, {len(transitions)} transitions")

    payload = build_discovery_payload(snapshots, transitions)

    Path(args.output).write_text(json.dumps(payload, indent=2))
    logger.info(f"Discovery payload written to {args.output}")

    # Print summary for GitHub Actions logs
    print(f"\n{'='*60}")
    print(f"DISCOVERY LAYER — {payload['snapshot_date']}")
    print(f"{'='*60}")
    if payload["transitions"]:
        print("\nSTAGE TRANSITIONS:")
        for t in payload["transitions"]:
            print(f"  {t['direction']} {t['topic_name']}: {t['from_stage']} → {t['to_stage']}")
    print(f"\nTOPIC SCORES ({payload['topic_count']} topics):")
    for t in payload["topics"]:
        print(f"  #{t['rank']:2d} {t['name']:<35s} {t['score']:3d}  {t['delta']['value']:<5s}  {t['stage']['label']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
