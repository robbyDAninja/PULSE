#!/usr/bin/env python3
"""
Pattern Analysis Generator — Bridge Ninja Intelligence Platform.

Reads the week's top signals from Supabase, feeds them to Claude with
the Bridge Ninja lens, and produces 3-5 pattern observations connecting
dots across topics and sources.

Runs Monday alongside generate_pulse.py and generate_discovery.py.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_patterns")


def get_top_signals(client, hours: int = 168) -> list[dict]:
    """Get the highest-engagement signals from the past week."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return (
        client.schema("intelligence")
        .table("signals")
        .select("title, source_type, source_url, points_or_stars, metadata, topics!inner(name, slug, category)")
        .gte("discovered_at", since)
        .order("points_or_stars", desc=True)
        .limit(200)
        .execute()
        .data
    )


def get_cross_topic_stories(client, hours: int = 168) -> list[dict]:
    """Find stories that appear under multiple topics (convergence signal)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # Get all HN/RSS signals with their topics
    signals = (
        client.schema("intelligence")
        .table("signals")
        .select("title, source_url, points_or_stars, source_type, topics!inner(name)")
        .gte("discovered_at", since)
        .in_("source_type", ["hackernews", "rss"])
        .order("points_or_stars", desc=True)
        .limit(500)
        .execute()
        .data
    )

    # Group by title to find cross-topic stories
    by_title: dict[str, dict] = {}
    for s in signals:
        title = s.get("title", "")
        if not title:
            continue
        if title not in by_title:
            by_title[title] = {
                "title": title,
                "url": s.get("source_url", ""),
                "points": s.get("points_or_stars") or 0,
                "source_type": s.get("source_type", ""),
                "topics": set(),
            }
        by_title[title]["topics"].add(s.get("topics", {}).get("name", ""))
        by_title[title]["points"] = max(by_title[title]["points"], s.get("points_or_stars") or 0)

    # Filter to stories hitting 2+ topics
    convergent = [
        {**v, "topics": list(v["topics"]), "topic_count": len(v["topics"])}
        for v in by_title.values()
        if len(v["topics"]) >= 2
    ]
    convergent.sort(key=lambda x: (x["topic_count"], x["points"]), reverse=True)
    return convergent[:20]


def get_top_hf_models(client, hours: int = 168) -> list[dict]:
    """Get top Hugging Face models from the collection period."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return (
        client.schema("intelligence")
        .table("signals")
        .select("title, points_or_stars, metadata, topics!inner(name)")
        .gte("discovered_at", since)
        .eq("source_type", "huggingface")
        .order("points_or_stars", desc=True)
        .limit(20)
        .execute()
        .data
    )


def get_snapshots_with_transitions(client) -> dict:
    """Get latest snapshots and any recent stage transitions."""
    # Latest snapshots
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
        return {"snapshots": [], "transitions": []}

    snapshot_date = latest[0]["snapshot_date"]
    snapshots = (
        client.schema("intelligence")
        .table("snapshots")
        .select("composite_score, score_delta, stage, hn_mentions, github_stars, news_mention_count, topics!inner(name, category)")
        .eq("snapshot_date", snapshot_date)
        .order("composite_score", desc=True)
        .execute()
        .data
    )

    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    transitions = (
        client.schema("intelligence")
        .table("stage_transitions")
        .select("from_stage, to_stage, topics!inner(name)")
        .gte("transitioned_at", since)
        .execute()
        .data
    )

    return {"snapshots": snapshots, "transitions": transitions}


def build_prompt(top_signals, cross_topic, hf_models, snapshot_data) -> str:
    """Build the Claude prompt for pattern analysis."""

    # Format top signals
    signal_lines = []
    for s in top_signals[:50]:
        topic = s.get("topics", {}).get("name", "Unknown")
        source = s.get("source_type", "")
        points = s.get("points_or_stars") or 0
        title = s.get("title", "")
        signal_lines.append(f"- [{source}] ({points} pts) {title} — Topic: {topic}")

    # Format cross-topic convergence
    convergence_lines = []
    for c in cross_topic[:10]:
        topics_str = ", ".join(c["topics"])
        convergence_lines.append(
            f"- ({c['points']} pts, {c['topic_count']} topics) \"{c['title']}\" — Crosses: {topics_str}"
        )

    # Format HF models
    hf_lines = []
    for m in hf_models[:10]:
        downloads = m.get("metadata", {}).get("downloads", 0)
        pipeline = m.get("metadata", {}).get("pipeline_tag", "")
        hf_lines.append(f"- {m['title']} ({m.get('points_or_stars', 0)} likes, {downloads:,} downloads) [{pipeline}]")

    # Format snapshot summary
    snapshot_lines = []
    for s in snapshot_data.get("snapshots", [])[:17]:
        topic = s.get("topics", {}).get("name", "")
        score = s.get("composite_score", 0)
        stage = s.get("stage", "")
        snapshot_lines.append(f"- {topic}: score {score}, stage: {stage}")

    transition_lines = []
    for t in snapshot_data.get("transitions", []):
        topic = t.get("topics", {}).get("name", "")
        transition_lines.append(f"- {topic}: {t['from_stage']} → {t['to_stage']}")

    return f"""You are a senior intelligence analyst for Bridge Ninja, a company that builds
human-centric organizations with AI-centric workflows. Your reader is the founder,
who needs to understand patterns — not just news — to stay ahead of the AI landscape.

Bridge Ninja's thesis: AI should amplify humans, not replace them. The goal is human
flourishing — creativity, autonomy, self-efficacy — enabled by AI handling the mundane.
When "zero-human" tools emerge, the question is: "What happens if we give this to
humans instead of using it to replace them?"

Below is the week's intelligence data from 17 tracked topics across GitHub, Hacker News,
Hugging Face, and news sources. Analyze it and identify 3-5 PATTERNS — not individual
stories, but cross-cutting themes that connect multiple signals.

TOP SIGNALS (by engagement):
{chr(10).join(signal_lines)}

CROSS-TOPIC CONVERGENCE (stories hitting multiple topics):
{chr(10).join(convergence_lines) if convergence_lines else "None this period."}

HUGGING FACE TRENDING MODELS:
{chr(10).join(hf_lines) if hf_lines else "None this period."}

TOPIC SCORES:
{chr(10).join(snapshot_lines)}

STAGE TRANSITIONS THIS WEEK:
{chr(10).join(transition_lines) if transition_lines else "None this period."}

Write your analysis in this format:

## Pattern Analysis — [date range]

### Pattern 1: [Pattern Name]
[2-3 sentences explaining the pattern. What signals converge to reveal this?
Why does it matter for Bridge Ninja specifically? What should the founder
be thinking about or watching for next?]

### Pattern 2: [Pattern Name]
[Same format]

[Continue for 3-5 patterns total]

### What to Watch Next Week
[2-3 sentences about what to monitor based on these patterns]

RULES:
- Focus on PATTERNS, not individual news stories
- Always connect back to the Bridge Ninja lens (human-centric, AI-augmented)
- Be specific — cite the signals that form each pattern
- Be opinionated — say what matters and what doesn't
- Flag counter-narratives (things that challenge the thesis) honestly
- Keep the total analysis to a 3-minute read"""


def generate_patterns(top_signals, cross_topic, hf_models, snapshot_data) -> str:
    """Call Claude to generate pattern analysis."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return ""

    prompt = build_prompt(top_signals, cross_topic, hf_models, snapshot_data)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Generate Pattern Analysis")
    parser.add_argument("--output", "-o", default="patterns.md")
    parser.add_argument("--lookback-hours", type=int, default=168)
    args = parser.parse_args()

    try:
        supabase_client = db.get_client()
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        sys.exit(1)

    logger.info("=== Pattern Analysis Generation ===")

    top_signals = get_top_signals(supabase_client, args.lookback_hours)
    cross_topic = get_cross_topic_stories(supabase_client, args.lookback_hours)
    hf_models = get_top_hf_models(supabase_client, args.lookback_hours)
    snapshot_data = get_snapshots_with_transitions(supabase_client)

    logger.info(f"Inputs: {len(top_signals)} top signals, {len(cross_topic)} convergent stories, {len(hf_models)} HF models")

    if not top_signals:
        logger.warning("No signals found. Skipping pattern analysis.")
        Path(args.output).write_text("")
        return

    analysis = generate_patterns(top_signals, cross_topic, hf_models, snapshot_data)

    if analysis:
        Path(args.output).write_text(analysis)
        logger.info(f"Pattern analysis written to {args.output}")
        print(f"\n{'='*60}")
        print(analysis)
        print(f"{'='*60}\n")
    else:
        logger.error("Pattern analysis generation failed")
        Path(args.output).write_text("")


if __name__ == "__main__":
    main()
