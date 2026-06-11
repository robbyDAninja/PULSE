#!/usr/bin/env python3
"""
Content Pulse email — the slim Monday note.

Queries today's content_pulse run from content.* and sends a short email via
the send-pulse-email edge function: "N new angles this week → review in
/find-ideas." Deliberately minimal — the angles live in the backlog, not the
inbox.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PULSE_WEBHOOK_SECRET
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import httpx

from db import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("send_content_pulse_email")


def main():
    supabase_url = os.environ["SUPABASE_URL"]
    webhook_secret = os.environ["PULSE_WEBHOOK_SECRET"]
    client = get_client()

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
        logger.warning("No content_pulse source for today — skipping email")
        return

    source = sources[0]
    ideas = (
        client.schema("content").table("ideas")
        .select("title, metadata, confidence")
        .eq("source_id", source["id"])
        .execute()
        .data
    )
    if not ideas:
        logger.warning("Source has no ideas — skipping email")
        return

    icp = sum(1 for i in ideas if (i.get("metadata") or {}).get("provenance") == "ICP-voice")
    proof = len(ideas) - icp
    summary = (source.get("metadata") or {}).get("summary", "")

    lines = [
        f"# Content Pulse — {len(ideas)} new angles this week",
        "",
        f"_{summary}_" if summary else "",
        "",
        f"**{icp} ICP-voice · {proof} proof** — all waiting in the backlog.",
        "",
    ]
    for i in ideas:
        m = i.get("metadata") or {}
        lines.append(f"- **{i['title']}** ({m.get('provenance')} · {m.get('klt_job')})")
    lines += ["", "👉 Review them with `/find-ideas`."]

    payload = {
        "report_markdown": "\n".join(filter(None, lines)),
        "report_date": today,
        "subject": f"Content Pulse — {len(ideas)} new angles · {today}",
        "webhook_secret": webhook_secret,
    }

    logger.info(f"Sending content pulse email ({len(ideas)} angles)...")
    resp = httpx.post(f"{supabase_url}/functions/v1/send-pulse-email", json=payload, timeout=30)
    if resp.status_code == 200:
        logger.info(f"Email sent: {resp.json().get('message_id')}")
    else:
        logger.error(f"Email failed ({resp.status_code}): {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
