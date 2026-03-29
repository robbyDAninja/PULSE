#!/usr/bin/env python3
"""
Monday Email Sender — combines Discovery Layer + Pattern Analysis + Deep Pulse
into a single email via the send-pulse-email edge function.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sys
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("send_monday_email")


def main():
    supabase_url = os.environ["SUPABASE_URL"]
    webhook_secret = os.environ["PULSE_WEBHOOK_SECRET"]

    from datetime import datetime, timezone
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # --- Build report markdown: patterns + deep pulse ---
    parts = []

    # Pattern analysis
    patterns_path = Path("patterns.md")
    if patterns_path.exists() and patterns_path.stat().st_size > 0:
        logger.info("Including pattern analysis")
        parts.append(patterns_path.read_text())

    # Deep pulse report (latest .md in reports/)
    report_files = sorted(glob.glob("reports/*.md"), reverse=True)
    if report_files:
        latest_report = Path(report_files[0])
        report_date = latest_report.stem.split("-openclaw")[0]  # Extract date from filename
        logger.info(f"Including deep pulse: {latest_report.name}")
        parts.append(latest_report.read_text())

    report_markdown = "\n\n---\n\n".join(parts) if parts else None

    # --- Discovery layer ---
    discovery_layer = None
    discovery_path = Path("discovery_payload.json")
    if discovery_path.exists():
        try:
            discovery_layer = json.loads(discovery_path.read_text())
            logger.info("Including discovery layer")
        except json.JSONDecodeError:
            logger.warning("Invalid discovery_payload.json — skipping")

    if not report_markdown and not discovery_layer:
        logger.warning("No content to send — skipping email")
        return

    # --- Send ---
    payload = {
        "report_markdown": report_markdown,
        "report_date": report_date,
        "subject": f"Bridge Ninja Intelligence — {report_date}",
        "webhook_secret": webhook_secret,
        "discovery_layer": discovery_layer,
    }

    logger.info(f"Sending email for {report_date}...")
    resp = httpx.post(
        f"{supabase_url}/functions/v1/send-pulse-email",
        json=payload,
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        logger.info(f"Email sent: {data.get('message_id')}")
    else:
        logger.error(f"Email failed ({resp.status_code}): {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
