#!/usr/bin/env python3
"""
Content Pulse — Phase 1 of "Re-aim the Pulse".

Fetches SMB-owner pain feeds (ICP-voice) plus a light "abundance thinker"
seasoning layer (proof), synthesizes them through Claude into doctrine-tagged
content angles, and writes them to Supabase content.* mirroring the proven
`signal` pattern:

    one run  -> one content.sources row   (source_type='content_pulse')
    each angle -> one content.ideas row    (status='extracted')

Those `extracted` rows are what /find-ideas surfaces into the publishing engine.

Doctrine guardrail (publishing engine KLT rule): every angle is ICP-voice
(SMB pain in their own words) OR proof (a stat/thesis backing a POV Bridge
Ninja already holds) — never "here's a trend, write about it." Each angle
carries provenance + a mandatory bridge_ninja_twist that lands it at SMB
scale, tactical, human.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python generate_content_pulse.py                 # DRY RUN — prints, writes nothing
    python generate_content_pulse.py --write         # writes to Supabase
        (also needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser
import requests
import yaml

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "content_pulse.config.yml"


# --------------------------------------------------------------------------
# Config + feed fetching (mirrors generate_pulse.py)
# --------------------------------------------------------------------------
def load_config():
    if not CONFIG_PATH.exists():
        print(f"❌ {CONFIG_PATH.name} not found")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def parse_entry_date(entry):
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def fetch_feed(url, name, provenance, max_articles, user_agent):
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": user_agent})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠️  {name}: fetch failed — {e}")
        return []

    feed = feedparser.parse(resp.text)
    if not feed.entries:
        print(f"  ⚠️  {name}: no entries found")
        return []

    articles = []
    for entry in feed.entries[:max_articles]:
        articles.append({
            "title": entry.get("title", "Untitled"),
            "description": (entry.get("summary") or entry.get("description") or "")[:600],
            "link": entry.get("link", ""),
            "date": parse_entry_date(entry),
            "source": name,
            "provenance": provenance,
        })
    print(f"  ✅ {name}: {len(articles)} articles [{provenance}]")
    return articles


def fetch_all_feeds(config):
    settings = config["settings"]
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    print("Fetching content feeds...")
    articles = []
    for feed_cfg in config["feeds"]:
        articles.extend(fetch_feed(
            feed_cfg["url"],
            feed_cfg["name"],
            feed_cfg.get("provenance", "ICP-voice"),
            settings["max_articles_per_feed"],
            user_agent,
        ))
    return articles


def filter_by_date(articles, days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = [a for a in articles if a["date"] is None or a["date"] >= cutoff]
    kept.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return kept


def format_articles_for_prompt(articles):
    blocks = []
    for a in articles:
        date_str = a["date"].strftime("%Y-%m-%d") if a["date"] else "Unknown"
        blocks.append(
            f"[Source: {a['source']}] [Provenance: {a['provenance']}] [Date: {date_str}]\n"
            f"Title: {a['title']}\n"
            f"Description: {a['description']}\n"
            f"Link: {a['link']}\n---"
        )
    return "\n".join(blocks) if blocks else "(No articles available)"


# --------------------------------------------------------------------------
# Synthesis
# --------------------------------------------------------------------------
def build_prompt(articles_text, config):
    report = config["report"]
    settings = config["settings"]
    tax = config["taxonomy"]
    ratio = int(settings.get("icp_voice_target_ratio", 0.66) * 100)

    return f"""You are the content strategist for Bridge Ninja.

WHO WE ARE: {report['identity']}

THE UNDERCURRENT (our differentiator — every angle carries this, stated or
not): {report['philosophy']}

WHO WE SERVE (the ICP): {report['audience']}

OUR VOICE: {report['voice']}

Below are this week's articles, each tagged with a provenance hint
(ICP-voice or proof). Turn them into publish-ready content ANGLES for our
idea backlog. These feed a publishing engine with a strict doctrine — read
the rules before writing.

ARTICLES:
{articles_text}

═══════════════════════════════════════════════════════════════
DOCTRINE (non-negotiable — the publishing engine rejects violations):
═══════════════════════════════════════════════════════════════
1. Every angle is EITHER:
   • provenance="ICP-voice" — built from real SMB-owner pain in their own
     words. Put the actual quote/paraphrase in quotable_moments. OR
   • provenance="proof" — a stat or thesis that BACKS a point of view
     Bridge Ninja ALREADY holds (clear-the-noise, pro-work/anti-job, AI
     takes the bullshit not the jobs, harness-builder-not-hero, abundance
     at human scale).
2. NEVER "here's a trend, write about it." Trend-chasing is the failure mode.
3. The "abundance thinker" / Moonshots material (Diamandis, Salim Ismail,
   Wissner-Gross, Blundin) is SEASONING, not the message. Any angle sparked
   there MUST be translated by bridge_ninja_twist into SMB-scale, tactical,
   HUMAN relief. If it can't be, drop it. Never lead with paradigm-shift talk.
   BUT — the undercurrent above is not seasoning; it's the spine. The best
   angles make an owner feel both SEEN in their pain and HOPEFUL about what's
   possible without giving up their humanity. Pain opens the door; grounded
   hope is what they leave with.
4. Each angle declares ONE primary klt_job (Know | Like | Trust). "Hits all
   three" is the contamination tell — pick one.
5. Pain-led mix: roughly {ratio}% of angles should be provenance="ICP-voice".
   Only include a proof angle when it genuinely backs a POV we already hold.

═══════════════════════════════════════════════════════════════
OUTPUT — return ONLY a JSON object, no prose, no markdown fences:
═══════════════════════════════════════════════════════════════
{{
  "week_summary": "1-2 sentences on the through-line across this week's angles.",
  "angles": [
    {{
      "title": "Polished hook-title (headline a reader would click).",
      "hook": "2-3 sentence promise — the pain or insight + what they'll get.",
      "story": "2-4 sentences of the substance/example behind the angle.",
      "philosophy": "The deeper Bridge Ninja belief this expresses (1-2 sentences).",
      "bridge_ninja_twist": "OUR take — how this lands at SMB scale, tactical, human. MANDATORY.",
      "buckets": ["1-2 of: {', '.join(tax['buckets'])}"],
      "big_5_angle": "exactly one of: {', '.join(tax['big_5_angle'])}",
      "bridge_ninja_element": "short phrase, e.g. 'team members', 'flow', 'clear the noise'",
      "value_lens": ["2-3 short value tags, e.g. 'relief', 'transparency', 'human-AI collaboration'"],
      "messaging_pillar": "short positioning phrase capturing the angle's stance",
      "content_theme": "short theme label",
      "keywords": ["5-7 lowercase keyword phrases"],
      "quotable_moments": ["1-2 pulled quotes; for ICP-voice, the real owner pain quote"],
      "confidence": "one of: {', '.join(tax['confidence'])}",
      "provenance": "ICP-voice | proof",
      "klt_job": "Know | Like | Trust",
      "source_url": "the article link this angle came from"
    }}
  ]
}}

Produce between {settings['min_angles']} and {settings['max_angles']} angles.
Order them STRONGEST FIRST — the first angle is the one most worth a Monday-
morning POV post (rawest pain + clearest grounded-hope payoff).
Quality over quantity — if the week is thin, return fewer. Be specific, name
things, write in our voice. No invented facts beyond the articles above."""


def synthesize(articles_text, config):
    settings = config["settings"]
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=settings["model"],
        max_tokens=settings["max_tokens"],
        messages=[{"role": "user", "content": build_prompt(articles_text, config)}],
    )
    raw = message.content[0].text.strip()
    # Defensive: strip accidental markdown fences, grab the JSON object.
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        print("❌ Synthesis did not return JSON. Raw output:\n", raw[:2000])
        sys.exit(1)
    try:
        return json.loads(raw[start:end + 1]), settings["model"]
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse failed: {e}\nRaw:\n{raw[:2000]}")
        sys.exit(1)


# --------------------------------------------------------------------------
# Persistence — content.sources + content.ideas (mirrors the signal pattern)
# --------------------------------------------------------------------------
def build_rows(result, model, config, week_of):
    """Return (source_row, [idea_rows]) ready to insert. idea source_id is filled after the source insert."""
    feed_names = [f["name"] for f in config["feeds"]]
    source_row = {
        "source_type": "content_pulse",
        "title": f"Content Pulse — week of {week_of}",
        "source_date": datetime.now(timezone.utc).isoformat(),
        "status": "processed",
        "metadata": {
            "week_of": week_of,
            "summary": result.get("week_summary", ""),
            "feeds": feed_names,
        },
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    idea_rows = []
    for a in result.get("angles", []):
        # The model occasionally comma-joins two buckets into one string —
        # split them back into separate tags so the array stays clean.
        buckets = [b.strip() for entry in a.get("buckets", []) for b in str(entry).split(",") if b.strip()]
        idea_rows.append({
            "title": a["title"],
            "hook": a.get("hook", ""),
            "story": a.get("story", ""),
            "philosophy": a.get("philosophy", ""),
            "bridge_ninja_twist": a.get("bridge_ninja_twist", ""),
            "buckets": buckets,
            "big_5_angle": a.get("big_5_angle", ""),
            "bridge_ninja_element": a.get("bridge_ninja_element", ""),
            "value_lens": a.get("value_lens", []),
            "messaging_pillar": a.get("messaging_pillar", ""),
            "content_theme": a.get("content_theme", ""),
            "keywords": a.get("keywords", []),
            "quotable_moments": a.get("quotable_moments", []),
            "confidence": a.get("confidence", "medium"),
            "status": "extracted",  # the flag /find-ideas surfaces on
            "metadata": {
                "source": "content_pulse",
                "provenance": a.get("provenance"),
                "klt_job": a.get("klt_job"),
                "signal_url": a.get("source_url"),
                "extracted_at": now_iso,
                "extraction_model": model,
            },
        })
    return source_row, idea_rows


def write_rows(source_row, idea_rows):
    """Insert the source, then the linked ideas. Imports get_client lazily so dry runs need no Supabase."""
    from db import get_client

    client = get_client()
    src = client.schema("content").table("sources").insert(source_row).execute()
    source_id = src.data[0]["id"]
    for row in idea_rows:
        row["source_id"] = source_id
    inserted = client.schema("content").table("ideas").insert(idea_rows).execute()
    return source_id, len(inserted.data)


def print_dry_run(source_row, idea_rows):
    print("\n" + "=" * 60)
    print("DRY RUN — nothing written. This is what WOULD be inserted.")
    print("=" * 60)
    print(f"\ncontent.sources:\n{json.dumps(source_row, indent=2)}")
    icp = sum(1 for r in idea_rows if r["metadata"]["provenance"] == "ICP-voice")
    proof = len(idea_rows) - icp
    print(f"\ncontent.ideas: {len(idea_rows)} angles "
          f"({icp} ICP-voice, {proof} proof) — all status='extracted'")
    for i, r in enumerate(idea_rows, 1):
        m = r["metadata"]
        print(f"\n  [{i}] {r['title']}")
        print(f"      provenance={m['provenance']} · klt={m['klt_job']} · "
              f"buckets={r['buckets']} · confidence={r['confidence']}")
        print(f"      hook: {r['hook']}")
        print(f"      twist: {r['bridge_ninja_twist']}")
        if r["quotable_moments"]:
            print(f"      quote: {r['quotable_moments'][0]}")


# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate the Bridge Ninja Content Pulse.")
    parser.add_argument("--write", action="store_true",
                        help="Write to Supabase. Default is a dry run that writes nothing.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY not set")
        sys.exit(1)

    config = load_config()
    settings = config["settings"]

    articles = fetch_all_feeds(config)
    articles = filter_by_date(articles, settings["lookback_days"])
    print(f"\n📊 {len(articles)} articles in the {settings['lookback_days']}-day window")
    if len(articles) < 3:
        print("⚠️  Too few articles — quiet week, skipping.")
        return

    print("\n🤖 Synthesizing doctrine-tagged angles via Claude...")
    result, model = synthesize(format_articles_for_prompt(articles), config)

    week_of = (datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())).strftime("%Y-%m-%d")
    source_row, idea_rows = build_rows(result, model, config, week_of)

    if not idea_rows:
        print("⚠️  Synthesis produced no angles. Nothing to do.")
        return

    if not args.write:
        print_dry_run(source_row, idea_rows)
        print("\n✅ Dry run complete. Re-run with --write to persist.")
        return

    print(f"\n💾 Writing 1 source + {len(idea_rows)} ideas to content.*...")
    source_id, n = write_rows(source_row, idea_rows)
    print(f"✅ Wrote source {source_id} and {n} ideas (status='extracted'). "
          f"They'll surface in /find-ideas.")


if __name__ == "__main__":
    main()
