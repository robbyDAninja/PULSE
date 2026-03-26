#!/usr/bin/env python3
"""
Signal Collector — Bridge Ninja Intelligence Platform.

Orchestrates signal collection from GitHub, Hacker News, and RSS sources,
stores signals in Supabase, computes composite scores and snapshots,
and detects stage transitions.

Runs Tuesday + Friday via GitHub Actions (collect-signals.yml).

Usage:
    export SUPABASE_URL=https://...
    export SUPABASE_SERVICE_ROLE_KEY=...
    export GH_PAT=ghp_...
    python collect_signals.py [--lookback-hours 84]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import db  # noqa: E402
import scoring  # noqa: E402
from sources import github, hackernews, rss_feeds  # noqa: E402
from sources.base import Signal  # noqa: E402

# ── Logging setup ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("collect_signals")

SCRIPT_DIR = Path(__file__).parent

# ── Source modules ───────────────────────────────────────────────────
# Each module has a collect(topic_id, keywords, since, config, topic_metadata) interface.
# YouTube is Phase 2 — not included yet.

SOURCE_MODULES = [
    ("github", github),
    ("hackernews", hackernews),
    ("rss", rss_feeds),
]


# ── Config ───────────────────────────────────────────────────────────


def load_config() -> dict:
    """Load configuration from config.yml."""
    config_path = SCRIPT_DIR / "config.yml"
    if not config_path.exists():
        logger.error("config.yml not found")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


# ── Collection ───────────────────────────────────────────────────────


def collect_for_topic(
    topic: dict, since: datetime, config: dict
) -> tuple[list[Signal], list[dict]]:
    """Collect signals from all sources for a single topic. Never raises."""
    all_signals: list[Signal] = []
    errors: list[dict] = []
    topic_id = topic["id"]
    keywords = topic.get("keywords", [])
    topic_metadata = topic.get("metadata") or {}

    if not keywords:
        logger.warning(f"Topic '{topic.get('name')}' has no keywords — skipping")
        return all_signals, errors

    for source_name, module in SOURCE_MODULES:
        source_config = config.get("sources", {}).get(source_name, {})

        # Skip disabled sources
        if not source_config.get("enabled", True):
            logger.info(f"  {source_name}: disabled in config")
            continue

        try:
            signals = module.collect(
                topic_id=topic_id,
                keywords=keywords,
                since=since,
                config=source_config,
                topic_metadata=topic_metadata,
            )
            all_signals.extend(signals)
            logger.info(f"  {source_name}: {len(signals)} signals")
        except Exception as e:
            logger.error(f"  {source_name}: FAILED — {e}")
            errors.append({"source": source_name, "error": str(e)})

    return all_signals, errors


def deduplicate_signals(signals: list[Signal]) -> list[Signal]:
    """Deduplicate signals by (topic_id, source_type, source_url)."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[Signal] = []
    for sig in signals:
        key = (sig.topic_id, sig.source_type, sig.source_url)
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    return unique


# ── Aggregation ──────────────────────────────────────────────────────


def aggregate_signals(signals: list[Signal]) -> dict:
    """Aggregate a list of signals into snapshot summary fields.

    Returns a dict with the raw values the scoring engine expects.
    """
    github_signals = [s for s in signals if s.source_type == "github"]
    hn_signals = [s for s in signals if s.source_type == "hackernews"]
    rss_signals = [s for s in signals if s.source_type == "rss"]

    # GitHub: total star delta (sum of stars from found repos as proxy)
    # and fork delta from metadata
    github_stars = sum(
        (s.metadata.get("stars") or 0) for s in github_signals
    )
    github_forks = sum(
        (s.metadata.get("forks") or 0) for s in github_signals
    )

    # HN: mention count and max points
    hn_mentions = len(hn_signals)
    hn_max_points = max(
        ((s.points_or_stars or 0) for s in hn_signals), default=0
    )

    # RSS/news: mention count
    news_mention_count = len(rss_signals)

    # Cross-source: count distinct source types with at least one signal
    source_types_present = set(s.source_type for s in signals)
    source_categories_seen = len(source_types_present)

    # YouTube: Phase 2, always 0 for now
    youtube_video_count = 0

    return {
        "github_stars": github_stars,
        "github_star_delta": github_stars,  # First run: stars = delta
        "github_forks": github_forks,
        "github_fork_delta": github_forks,
        "hn_mentions": hn_mentions,
        "hn_max_points": hn_max_points,
        "youtube_video_count": youtube_video_count,
        "news_mention_count": news_mention_count,
        "rss_mention_count": news_mention_count,
        "source_count": source_categories_seen,
        "source_categories_seen": source_categories_seen,
    }


# ── Snapshot Building ────────────────────────────────────────────────


def build_snapshot(
    topic: dict,
    signals_summary: dict,
    prior_snapshot: dict | None,
    snapshot_date: str,
) -> dict:
    """Build a complete snapshot row for Supabase upsert."""
    # Run scoring engine
    score_result = scoring.score_snapshot(
        topic=topic,
        signals_summary=signals_summary,
        prior_snapshot=prior_snapshot,
    )

    # Adjust star/fork deltas if we have a prior snapshot
    if prior_snapshot:
        prior_stars = prior_snapshot.get("github_stars") or 0
        if prior_stars > 0 and signals_summary["github_stars"] > 0:
            signals_summary["github_star_delta"] = max(
                0, signals_summary["github_stars"] - prior_stars
            )
        prior_forks = prior_snapshot.get("github_forks") or 0
        if prior_forks > 0 and signals_summary["github_forks"] > 0:
            signals_summary["github_fork_delta"] = max(
                0, signals_summary["github_forks"] - prior_forks
            )
        # Re-score with adjusted deltas
        score_result = scoring.score_snapshot(
            topic=topic,
            signals_summary=signals_summary,
            prior_snapshot=prior_snapshot,
        )

    snapshot = {
        "topic_id": topic["id"],
        "snapshot_date": snapshot_date,
        "github_stars": signals_summary.get("github_stars", 0),
        "github_star_delta": signals_summary.get("github_star_delta", 0),
        "github_forks": signals_summary.get("github_forks", 0),
        "github_fork_delta": signals_summary.get("github_fork_delta", 0),
        "hn_mentions": signals_summary.get("hn_mentions", 0),
        "hn_max_points": signals_summary.get("hn_max_points", 0),
        "youtube_video_count": signals_summary.get("youtube_video_count", 0),
        "rss_mention_count": signals_summary.get("rss_mention_count", 0),
        "news_mention_count": signals_summary.get("news_mention_count", 0),
        "source_count": signals_summary.get("source_count", 0),
        "composite_score": score_result["composite_score"],
        "score_delta": score_result["score_delta"],
        "stage": score_result["stage"],
    }

    return snapshot


# ── Stage Transitions ────────────────────────────────────────────────


def check_stage_transition(
    topic: dict, snapshot: dict, prior_snapshot: dict | None
) -> dict | None:
    """Check if a stage transition occurred and return transition info."""
    current_stage = topic.get("current_stage", "emergence")
    new_stage = snapshot["stage"]

    if new_stage == current_stage:
        return None

    return {
        "topic_id": topic["id"],
        "topic_name": topic.get("name", "Unknown"),
        "from_stage": current_stage,
        "to_stage": new_stage,
    }


# ── Main ─────────────────────────────────────────────────────────────


def main():
    """Orchestrate the full signal collection pipeline."""
    parser = argparse.ArgumentParser(description="Collect signals for Bridge Ninja Intelligence")
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=None,
        help="How many hours to look back for signals (default: from config or 84)",
    )
    args = parser.parse_args()

    # --- Step 1: Initialize ---
    logger.info("=== Bridge Ninja Signal Collection ===")

    config = load_config()
    lookback_hours = (
        args.lookback_hours
        or config.get("collection", {}).get("lookback_hours", 84)
    )
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Lookback: {lookback_hours}h (since {since.isoformat()})")
    logger.info(f"Snapshot date: {snapshot_date}")

    # --- Initialize Supabase ---
    try:
        client = db.get_client()
        logger.info("Supabase client initialized")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        sys.exit(1)

    # --- Load topics ---
    try:
        topics = db.get_active_topics(client)
        if not topics:
            logger.error("No active topics found — exiting")
            sys.exit(1)
        logger.info(f"Loaded {len(topics)} active topics")
    except Exception as e:
        logger.error(f"Failed to load topics: {e}")
        sys.exit(1)

    # --- Step 2-3: Collect and store signals ---
    total_signals = 0
    total_errors = 0
    all_transitions: list[dict] = []

    for topic in topics:
        topic_name = topic.get("name", "Unknown")
        logger.info(f"\n--- {topic_name} ---")

        # Collect from all sources
        signals, errors = collect_for_topic(topic, since, config)
        total_errors += len(errors)

        # Deduplicate
        signals = deduplicate_signals(signals)
        logger.info(f"  Total (deduplicated): {len(signals)} signals")

        # Store signals in Supabase
        if signals:
            try:
                signal_rows = [s.to_db_row() for s in signals]
                stored = db.upsert_signals(client, signal_rows)
                total_signals += stored
                logger.info(f"  Stored: {stored} signals")
            except Exception as e:
                logger.error(f"  Failed to store signals: {e}")

        # --- Step 4: Compute snapshot ---
        signals_summary = aggregate_signals(signals)

        # Get prior snapshot for deltas
        try:
            prior_snapshot = db.get_latest_snapshot(client, topic["id"])
        except Exception as e:
            logger.warning(f"  Could not fetch prior snapshot: {e}")
            prior_snapshot = None

        snapshot = build_snapshot(topic, signals_summary, prior_snapshot, snapshot_date)

        # --- Step 5: Store snapshot ---
        try:
            stored_snapshot = db.upsert_snapshot(client, snapshot)
            logger.info(
                f"  Snapshot: score={snapshot['composite_score']:.1f} "
                f"(delta={snapshot['score_delta']:+.1f}) "
                f"stage={snapshot['stage']}"
            )
        except Exception as e:
            logger.error(f"  Failed to store snapshot: {e}")
            stored_snapshot = snapshot

        # --- Step 6: Check stage transitions ---
        transition = check_stage_transition(topic, snapshot, prior_snapshot)
        if transition:
            logger.info(
                f"  STAGE TRANSITION: {transition['from_stage']} -> {transition['to_stage']}"
            )
            all_transitions.append(transition)

            # Record transition in Supabase
            try:
                snapshot_id = stored_snapshot.get("id")
                db.insert_stage_transition(
                    client,
                    topic_id=topic["id"],
                    from_stage=transition["from_stage"],
                    to_stage=transition["to_stage"],
                    snapshot_id=snapshot_id,
                    notes=f"Auto-detected: {transition['from_stage']} -> {transition['to_stage']}",
                )
                db.update_topic_stage(client, topic["id"], transition["to_stage"])
            except Exception as e:
                logger.error(f"  Failed to record transition: {e}")

    # --- Step 7: Summary ---
    logger.info("\n=== Collection Summary ===")
    logger.info(f"Topics processed: {len(topics)}")
    logger.info(f"Signals stored: {total_signals}")
    logger.info(f"Source errors: {total_errors}")
    logger.info(f"Stage transitions: {len(all_transitions)}")

    if all_transitions:
        logger.info("\nTransitions:")
        for t in all_transitions:
            logger.info(
                f"  {t['topic_name']}: {t['from_stage']} -> {t['to_stage']}"
            )

    logger.info("\n=== Done ===")


if __name__ == "__main__":
    main()
