#!/usr/bin/env python3
"""
Trajectory — Tue/Fri personal briefing.

Replaces the old signal brief. Pulls the collection window from
intelligence.signals, pre-trims to the most credible signals (primary-source
domains first, then by community traction), and asks Claude to select the 3-5
that genuinely matter, framed as trajectories through a grounded-hope lens.

No composite scores, no stages — selection is entirely editorial, governed by
the prompt (canonical copy: docs/briefing-prompt.md).

Usage:
    python generate_briefing.py             # generate and send
    python generate_briefing.py --dry-run   # print the briefing, send nothing
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import anthropic
import httpx
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("briefing")

CONFIG_PATH = Path(__file__).parent / "config.yml"

# Announcements from these domains pre-survived a mature internal filter —
# they always make the shortlist regardless of points.
PRIMARY_DOMAINS = (
    "anthropic.com",
    "openai.com",
    "deepmind.google",
    "blog.google",
    "research.google",
    "apple.com",
    "nvidia.com",
    "microsoft.com",
    "meta.com",
    "ai.meta.com",
    "huggingface.co",
)

PROMPT = """You are the editor of **Trajectory**, a twice-weekly (Tue/Fri) personal briefing for one reader: Robby — founder of Bridge Ninja, where he teaches small businesses to actually use AI (Claude) in their operations.

THE READER
- He chooses optimism and hope deliberately. Not naive hype — grounded hope: technology is drastically expanding what's possible in health, medicine, fitness, finances, and human capability, and he wants to watch that unfold in real time.
- He is training a skill: pattern recognition. Seeing the line from where we came from, to where we are, to where we're going. Every item you include should exercise that muscle.
- His time budget is a glance: two minutes, then back to work. You are the opposite of a news feed — nothing optimized for engagement, nothing that pokes at lower interests.

YOUR JOB
From the raw signals below (RSS, Hacker News, GitHub, Hugging Face, arXiv from the last ~3.5 days), choose the 3-5 that genuinely matter and frame each as a trajectory.

SELECTION RULES (priority order)
1. Primary announcements from mature filters first: Anthropic, OpenAI, Google/DeepMind, Apple, Meta, NVIDIA, Microsoft. If a big lab shipped it, it already survived their internal noise filter.
2. Real capability unlocks over incremental model-bump news — especially in health, medicine, fitness, finance, robotics, and tools that put new capability in ordinary hands.
3. Relevant to a person teaching SMBs to use Claude: agent patterns, Claude ecosystem shifts, normal businesses doing extraordinary things with AI.
4. High-signal community evidence (e.g. an HN thread with unusual traction) only when it reveals something the press hasn't.

HARD EXCLUSIONS — never include
- Entertainment: shows, movies, celebrity, gaming culture. Interesting is not the same as worth his attention; he explicitly does not want his lower interests fed.
- Industry drama, feuds, executive moves, funding-round gossip.
- Gadget rumors or speculation about unannounced products.
- GitHub repos that merely keyword-match a topic. A repo earns inclusion only with strong evidence of real adoption.
- Doom takes and outrage bait, including AI-doom content with no actionable substance.

WRITE EACH ITEM AS
- A plain-English headline in your own words — no clickbait inheritance from the source.
- One or two sentences of trajectory: what this used to take, what just changed, what it points toward. Anchor in the concrete.
- Honesty discipline: distinguish shipped from announced from claimed. Never present a company's claim as verified fact — write "Google says...", not "Google achieved...". Grounded hope survives scrutiny; hype doesn't.

THEN ONE CLOSING LINE
The thread: a single sentence connecting this briefing's items into one pattern — the where-we're-going line. If no honest thread exists, skip it. Never force one.

QUIET PERIODS
If fewer than 3 items genuinely qualify, send fewer. One real signal beats five padded ones. If nothing qualifies, say exactly that in one sentence — that is a successful briefing, not a failure.

LENGTH
The whole briefing must read in under two minutes. About 250 words maximum.

OUTPUT FORMAT — exactly this structure, nothing else. No preamble, no sign-off, no code fences.

**<headline>**
<trajectory sentence(s)> ([<source>](<url>))

(blank line between items)

**The thread:** <one sentence — only if honest>

RAW SIGNALS
{signals}"""


def load_settings() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config.get("briefing", {})


def is_primary(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in PRIMARY_DOMAINS)


def get_window_signals(client, hours: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return (
        client.schema("intelligence")
        .table("signals")
        .select("title, source_url, source_type, points_or_stars, topics!inner(name)")
        .gte("discovered_at", since)
        .order("points_or_stars", desc=True)
        .limit(3000)
        .execute()
        .data
    )


def shortlist(signals: list[dict], max_signals: int) -> list[dict]:
    """Dedupe by URL, then primary-source signals first, rest by traction."""
    seen: set[str] = set()
    deduped = []
    for sig in signals:
        url = sig.get("source_url") or ""
        if url and url in seen:
            continue
        seen.add(url)
        deduped.append(sig)

    primary = [s for s in deduped if is_primary(s.get("source_url") or "")]
    rest = [s for s in deduped if not is_primary(s.get("source_url") or "")]
    return (primary + rest)[:max_signals]


def format_signals(signals: list[dict]) -> str:
    lines = []
    for sig in signals:
        title = (sig.get("title") or "Untitled")[:160]
        source = sig.get("source_type") or "unknown"
        points = sig.get("points_or_stars")
        topic = sig.get("topics", {}).get("name", "")
        tag = " [PRIMARY SOURCE]" if is_primary(sig.get("source_url") or "") else ""
        pts = f" ({points} pts)" if points else ""
        lines.append(f"- [{source}]{tag} {title}{pts} | {sig.get('source_url', '')} | topic: {topic}")
    return "\n".join(lines)


def synthesize(signals_text: str, settings: dict) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=settings.get("model", "claude-sonnet-4-6"),
        max_tokens=settings.get("max_tokens", 2000),
        messages=[{"role": "user", "content": PROMPT.format(signals=signals_text)}],
    )
    return message.content[0].text.strip()


def send_briefing(markdown: str, date_str: str) -> bool:
    supabase_url = os.environ["SUPABASE_URL"]
    webhook_secret = os.environ.get("PULSE_WEBHOOK_SECRET", "")

    resp = httpx.post(
        f"{supabase_url}/functions/v1/send-pulse-email",
        json={
            "report_date": date_str,
            "subject": f"Trajectory — {date_str}",
            "webhook_secret": webhook_secret,
            "report_markdown": markdown,
        },
        timeout=30,
    )
    if resp.status_code == 200:
        logger.info(f"Briefing sent: {resp.json().get('message_id')}")
        return True
    logger.error(f"Failed to send briefing: {resp.status_code} {resp.text}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Generate and send the Trajectory briefing")
    parser.add_argument("--dry-run", action="store_true", help="Print the briefing, send nothing")
    args = parser.parse_args()

    settings = load_settings()
    lookback = settings.get("lookback_hours", 96)
    max_signals = settings.get("max_signals", 150)

    client = db.get_client()
    signals = get_window_signals(client, lookback)
    if not signals:
        logger.info("No signals in window — skipping briefing.")
        return

    shortlisted = shortlist(signals, max_signals)
    n_primary = sum(1 for s in shortlisted if is_primary(s.get("source_url") or ""))
    logger.info(
        f"{len(signals)} signals in window → {len(shortlisted)} shortlisted ({n_primary} primary-source)"
    )

    briefing = synthesize(format_signals(shortlisted), settings)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.dry_run:
        print(f"\n--- Trajectory — {date_str} (dry run) ---\n")
        print(briefing)
        print("\n--- end ---")
        return

    if not send_briefing(briefing, date_str):
        sys.exit(1)


if __name__ == "__main__":
    main()
