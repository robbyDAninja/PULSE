#!/usr/bin/env python3
"""
Content Pulse email — the Monday POV-drafting briefing.

Not a receipt. The job of this email (Robby, 2026-06-11): make Monday's
30-45-minute POV drafting session start itself — the week's through-line,
the rawest owner quotes, and the lead angle teed up ready to write.

Queries today's content_pulse run from content.* and sends via the
send-pulse-email edge function.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PULSE_WEBHOOK_SECRET
Flags: --dry-run prints the markdown instead of sending (no webhook needed).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import httpx

from db import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("send_content_pulse_email")

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def fetch_todays_run(client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources = (
        client.schema("content").table("sources")
        .select("id, title, metadata")
        .eq("source_type", "content_pulse")
        .gte("source_date", f"{today}T00:00:00Z")
        .order("source_date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not sources:
        return None, []
    source = sources[0]
    ideas = (
        client.schema("content").table("ideas")
        .select("title, hook, story, bridge_ninja_twist, philosophy, quotable_moments, "
                "confidence, metadata, created_at")
        .eq("source_id", source["id"])
        .order("created_at")
        .execute()
        .data
    )
    return source, ideas


def pick_lead(ideas):
    """Lead = strongest angle. Synthesis orders strongest-first; fall back to
    confidence rank with ICP-voice preferred for older runs."""
    def key(pair):
        i, idea = pair
        m = idea.get("metadata") or {}
        return (
            CONFIDENCE_RANK.get(idea.get("confidence"), 3),
            0 if m.get("provenance") == "ICP-voice" else 1,
            i,
        )
    return min(enumerate(ideas), key=key)[1]


def collect_quotes(ideas, lead, limit=3):
    """Rawest ICP-voice quotes from the week, excluding the lead's own (it
    appears in the lead block)."""
    quotes = []
    for idea in ideas:
        if idea is lead:
            continue
        m = idea.get("metadata") or {}
        if m.get("provenance") != "ICP-voice":
            continue
        for q in idea.get("quotable_moments") or []:
            q = q.strip().strip('"')
            if q and q not in quotes:
                quotes.append(q)
                break  # one per angle — spread the voices
        if len(quotes) >= limit:
            break
    return quotes


def build_markdown(source, ideas):
    meta = source.get("metadata") or {}
    summary = meta.get("summary", "").strip()
    lead = pick_lead(ideas)
    lead_meta = lead.get("metadata") or {}
    quotes = collect_quotes(ideas, lead)
    rest = [i for i in ideas if i is not lead]

    lines = ["# This week in your ICP's head", ""]
    if summary:
        lines += [f"**The through-line:** {summary}", ""]

    if quotes:
        lines += ["## What owners are actually saying", ""]
        for q in quotes:
            lines += [f'> "{q}"', ""]

    lines += [
        "## Your POV draft, teed up",
        "",
        f"### {lead['title']}",
        "",
        lead.get("hook", ""),
        "",
        lead.get("story", ""),
        "",
    ]
    lead_quotes = lead.get("quotable_moments") or []
    if lead_quotes:
        lines += [f'> "{lead_quotes[0].strip().strip(chr(34))}"', ""]
    if lead.get("bridge_ninja_twist"):
        lines += [f"**The Bridge Ninja take:** {lead['bridge_ninja_twist']}", ""]
    lines += [
        f"_{lead_meta.get('provenance')} · {lead_meta.get('klt_job')} · "
        f"{lead.get('confidence')} confidence_",
        "",
    ]

    if rest:
        lines += ["## Also in the backlog this week", ""]
        for idea in rest:
            m = idea.get("metadata") or {}
            lines.append(f"- **{idea['title']}** — {m.get('provenance')} · {m.get('klt_job')}")
        lines.append("")

    lines += [
        "---",
        "",
        f"_All {len(ideas)} angles (full hooks, stories, quotes) are in the "
        "`content.ideas` backlog. Thirty minutes, one post — pick one and go._",
    ]
    return "\n".join(lines), lead


def main():
    parser = argparse.ArgumentParser(description="Send the Content Pulse Monday briefing.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the email markdown instead of sending.")
    args = parser.parse_args()

    client = get_client()
    source, ideas = fetch_todays_run(client)
    if not source:
        logger.warning("No content_pulse source for today — skipping email")
        return
    if not ideas:
        logger.warning("Source has no ideas — skipping email")
        return

    markdown, lead = build_markdown(source, ideas)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"Monday Pulse: {lead['title']}"

    if args.dry_run:
        print(f"SUBJECT: {subject}\n\n{markdown}")
        return

    payload = {
        "report_markdown": markdown,
        "report_date": today,
        "subject": subject,
        "webhook_secret": os.environ["PULSE_WEBHOOK_SECRET"],
    }
    logger.info(f"Sending Monday briefing ({len(ideas)} angles, lead: {lead['title'][:50]})...")
    resp = httpx.post(
        f"{os.environ['SUPABASE_URL']}/functions/v1/send-pulse-email",
        json=payload, timeout=30,
    )
    if resp.status_code == 200:
        logger.info(f"Email sent: {resp.json().get('message_id')}")
    else:
        logger.error(f"Email failed ({resp.status_code}): {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
