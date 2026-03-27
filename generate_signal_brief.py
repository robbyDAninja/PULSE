#!/usr/bin/env python3
"""
Signal Brief — lightweight Tue/Fri email with top stories from collection.

No Claude synthesis — just the most notable signals captured this period,
grouped by topic, with links. Scannable in 1-2 minutes.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("signal_brief")

# Only show topics that had notable signals
MIN_POINTS_TO_SHOW = 10  # HN/GitHub threshold
MAX_STORIES_PER_TOPIC = 3
MAX_TOPICS = 10


def get_recent_signals(client, hours: int = 84) -> list[dict]:
    """Get signals from the last collection window."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return (
        client.schema("intelligence")
        .table("signals")
        .select("*, topics!inner(name, slug, category)")
        .gte("discovered_at", since)
        .order("points_or_stars", desc=True)
        .limit(500)
        .execute()
        .data
    )


def get_latest_snapshots(client) -> dict:
    """Get latest snapshot scores keyed by topic name."""
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
        return {}
    snapshots = (
        client.schema("intelligence")
        .table("snapshots")
        .select("composite_score, stage, topics!inner(name)")
        .eq("snapshot_date", latest[0]["snapshot_date"])
        .execute()
        .data
    )
    return {s["topics"]["name"]: s for s in snapshots}


def group_by_topic(signals: list[dict]) -> dict[str, list[dict]]:
    """Group signals by topic, keeping only the most notable."""
    groups: dict[str, list[dict]] = {}
    for sig in signals:
        topic_name = sig.get("topics", {}).get("name", "Unknown")
        if topic_name not in groups:
            groups[topic_name] = []
        groups[topic_name].append(sig)
    return groups


def build_brief_html(grouped: dict[str, list[dict]], scores: dict) -> str:
    """Build the signal brief HTML."""
    html = ""

    # Sort topics by number of signals (most active first)
    sorted_topics = sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)

    topics_shown = 0
    for topic_name, signals in sorted_topics:
        if topics_shown >= MAX_TOPICS:
            break

        # Filter to notable signals
        notable = [s for s in signals if (s.get("points_or_stars") or 0) >= MIN_POINTS_TO_SHOW]
        if not notable and not signals:
            continue

        # Get score info
        score_info = scores.get(topic_name, {})
        stage = (score_info.get("stage") or "").title()

        # Stage badge colors
        stage_colors = {
            "Emergence": ("#e5e7eb", "#374151"),
            "Traction": ("#dbeafe", "#1e40af"),
            "Inflection": ("#fef3c7", "#92400e"),
        }
        bg, fg = stage_colors.get(stage, ("#e5e7eb", "#374151"))

        html += f'<div style="margin-bottom: 20px;">'
        html += f'<div style="display: flex; align-items: center; margin-bottom: 6px;">'
        html += f'<strong style="font-size: 15px;">{topic_name}</strong>'
        if stage:
            html += f'<span style="background: {bg}; color: {fg}; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 8px;">{stage}</span>'
        html += f'<span style="color: #9ca3af; font-size: 12px; margin-left: 8px;">{len(signals)} signal{"s" if len(signals) != 1 else ""}</span>'
        html += '</div>'

        # Show top stories
        shown = notable[:MAX_STORIES_PER_TOPIC] if notable else signals[:2]
        for sig in shown:
            title = sig.get("title", "Untitled")
            url = sig.get("source_url", "")
            source = (sig.get("source_type") or "").replace("_", " ").title()
            points = sig.get("points_or_stars")
            points_str = f' <span style="color: #d97706; font-size: 11px;">({points} pts)</span>' if points else ""

            if url:
                html += f'<div style="margin-left: 12px; margin-bottom: 4px; font-size: 13px; line-height: 1.4;">'
                html += f'<span style="color: #9ca3af; font-size: 11px;">{source}</span> '
                html += f'<a href="{url}" style="color: #2563eb; text-decoration: none;">{title}</a>{points_str}'
                html += '</div>'
            else:
                html += f'<div style="margin-left: 12px; margin-bottom: 4px; font-size: 13px;">'
                html += f'<span style="color: #9ca3af; font-size: 11px;">{source}</span> {title}{points_str}'
                html += '</div>'

        html += '</div>'
        topics_shown += 1

    if topics_shown == 0:
        html = '<p style="color: #6b7280;">Quiet period — no notable signals captured.</p>'

    return html


def send_brief(html_body: str, date_str: str) -> bool:
    """Send the brief via the existing edge function."""
    supabase_url = os.environ["SUPABASE_URL"]
    webhook_secret = os.environ.get("PULSE_WEBHOOK_SECRET", "")

    # Wrap signal list in a brief header/footer via markdown
    brief_md = (
        f"## What Hit the Radar — {date_str}\n\n"
        f"{html_body}\n\n"
        f"---\n*Full synthesis arrives Monday.*"
    )

    resp = httpx.post(
        f"{supabase_url}/functions/v1/send-pulse-email",
        json={
            "report_date": date_str,
            "subject": f"Signal Brief — {date_str}",
            "webhook_secret": webhook_secret,
            "report_markdown": brief_md,
        },
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        logger.info(f"Brief sent: {data.get('message_id')}")
        return True
    else:
        logger.error(f"Failed to send brief: {resp.status_code} {resp.text}")
        return False


def main():
    try:
        client = db.get_client()
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        sys.exit(1)

    logger.info("=== Signal Brief Generation ===")

    signals = get_recent_signals(client)
    if not signals:
        logger.info("No signals found. Skipping brief.")
        return

    scores = get_latest_snapshots(client)
    grouped = group_by_topic(signals)

    logger.info(f"Found {len(signals)} signals across {len(grouped)} topics")

    html = build_brief_html(grouped, scores)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if send_brief(html, date_str):
        logger.info("Signal brief sent successfully.")
    else:
        logger.error("Failed to send signal brief.")
        sys.exit(1)


if __name__ == "__main__":
    main()
