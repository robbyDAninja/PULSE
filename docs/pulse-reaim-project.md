---
version: 0.5
last_updated: 2026-06-11
status: active
linear_project: https://linear.app/bridge-ninja/project/re-aim-the-pulse-cdcd0cddb070
---

# Project: Re-aim the Pulse

**Goal:** Re-point the (well-built but mis-aimed) Pulse from "AI-agent-framework
ecosystem tracking for a builder" → two strategy-serving outputs.

Linear: **Re-aim the Pulse** (BRI). Issues BRI-100…105.

## Why

The machinery is good (RSS synthesis + a scored signal layer, Haiku, evidence-grounded
prompt). But its config defined its reader as "a builder deploying Luma tracking OpenClaw
patterns" — Robby-the-tinkerer, not Bridge-Ninja-the-business. ~80% of tracked topics had
near-zero tie to selling AI operating systems to marketing agencies. Reliable, rarely useful.

## The two tracks (the organizing frame)

| Track | Destination | Feeds | Sources |
|---|---|---|---|
| **Content** | `content.ideas` | publishing engine | `fireflies` (meetings) · `signal` (CC working sessions) · `manual` · **`content_pulse`** (new web scrape) |
| **Strategy** | `intelligence.*` | flywheel / Council | the 19 momentum topics |

Signal and Intelligence *feel* related (both "good ideas I built and forgot") but live on
**opposite tracks** — do NOT restructure them together.

## Verified state (queried live 2026-06-02)

- `intelligence.*` is **alive and accumulating**: 36,563 signals (Mar 20 → today), 8,105 in
  last 14 days, 391 weekly snapshots, 15 stage transitions, 19 topics. Twice-weekly. Never
  surfaced to Robby in a usable form → the real gap.
- 4 of the 19 topics are on-thesis (Enterprise AI Adoption 2.7k, AI Workforce Integration 1.6k,
  AI-Powered Business Building 1.3k, AI + Human Flourishing 1.2k) — a proof-point mine.
- `content.ideas` already holds 75 ideas across 3 coexisting source_types: `signal` (60,
  CC-session extraction via the Signal skill), `fireflies` (10, meetings), `manual` (5).
  Columns map ~1:1 to the angle format. **Zero schema surgery needed** — Phase 1 just adds
  source_type `content_pulse`.

## Doctrine guardrail (publishing engine KLT rule)

Publishing rejects trend-chasing ("engagement does not steer content"). Pulse angles must be
**ICP-voice** (agency pain in their own words) or **proof** (stats backing POVs BN already
holds) — never "here's a trend, chase it." Each angle tagged `provenance=[ICP-voice|proof]`.
Conform to their taxonomy: Buckets (6 pillars) + KLT job (Know/Like/Trust).

## Phasing (Linear)

- **BRI-100 Phase 1 — Content angles** *(active — BUILT, dry-run validated 2026-06-04)*:
  `content_pulse` → `content.ideas`, modeled on the proven `signal` pattern. Script + config
  written, first real dry run produced 6 doctrine-clean angles (5 ICP-voice / 1 proof). See
  "Phase 1 build state" below. Remaining: `--write` a real run, wire to CI, slim the email.
- BRI-101 Phase 2 — Competitive + thesis watch
- BRI-102 Phase 3 — Sales / prospect intel
- BRI-103 Phase 4 — Movement / narrative
- **BRI-104 PARKED** — Strategy track: intelligence re-leverage (mine + re-point 19 topics +
  wire to flywheel). Leave running untouched. Deferred deliberately (would distract).
- **BRI-105 PARKED** — Content-sources tidy-up: Signal automation + reconcile sources. Signal
  is reused, not deprecated — it's the prototype `content_pulse` productizes.

## Phase 1 build state (2026-06-04)

**ICP corrected (Robby, 2026-06-02):** target is **SMBs (small-and-medium business owners)**, NOT
marketing agencies. Agencies were an old framing. ⚠️ The formal KB doc
`knowledge-base/brand/IDEAL-CLIENT-PROFILE.md` (Apr 11) still says "seven-figure agencies" — it
lags Robby's current intent. Needs a separate update (candidate parked ticket).

**Influence anchor (Robby):** piggyback the Moonshots / abundance cluster — Diamandis, Salim Ismail,
Alex Wissner-Gross, Dave Blundin — as **proof seasoning**, then translate to SMB-scale relief.
Already doctrine per `archive/legacy-internal/SOLVE_EVERYTHING_BRIDGE.md` ("use in thought-leadership,
NOT sales; don't lead with paradigm shift"). Decisions: **SMB-only** (drop agency feeds) +
**pain-led, Moonshots as seasoning** (~2/3 ICP-voice).

**Files built (uncommitted as of close):**
- `generate_content_pulse.py` — fetch → Claude synthesizes JSON angles → write source+ideas.
  Defaults to `--dry-run` (writes nothing); `--write` persists. Imports `get_client` from `db.py`.
- `content_pulse.config.yml` — locked source set + identity/voice + canonical `content.ideas` vocab.
- `reports/content-pulse-dry-run-2026-06-02.html` — the dry-run results report shown to Robby.

**Locked source set** (all fetch-verified): ICP-voice → r/smallbusiness, r/Entrepreneur (both
`top/.rss?t=week`), Google News SMB-owner-pain query · proof → Moonshots podcast
(`feeds.megaphone.fm/DVVTS2890392624`), Google News abundance-thinkers query, Google News
McKinsey/Gartner "AI adoption" query. Diamandis blog dropped (stale). Agency subreddits dropped.

**Locked record shape (verified live against the 75 proven rows — don't re-query):**
- `content.sources`: insert `source_type='content_pulse'`, `title`, `source_date`,
  `status='processed'` (what `signal` sources use), `metadata={week_of, summary, feeds[]}`.
  Required NOT NULL: `source_type`.
- `content.ideas`: one row per angle, `status='extracted'` (THE flag `/find-ideas` surfaces),
  `source_id`→the source. Full column set populated: title, hook, story, philosophy,
  bridge_ninja_twist, buckets[], big_5_angle, bridge_ninja_element, value_lens[], messaging_pillar,
  content_theme, keywords[], quotable_moments[], confidence, metadata. Required NOT NULL:
  source_id, title. `metadata={source:'content_pulse', provenance, klt_job, signal_url,
  extracted_at, extraction_model}`.
- **`buckets[]` taxonomy resolved:** uses the emergent `signal` vocabulary (Philosophy & What-Ifs,
  Business Building Reality, Behind the Breakthrough, AI & Human Psychology, Systems Philosophy,
  Best in Class, Problems, Pricing/Costs, Versus/Comparisons, Reviews/Assessments) — **NOT** the
  Box `CONTENT-STRATEGY.md` 7-pillar marketing taxonomy. Those are two different systems.
- Write path: `supabase-py` via `client.schema("content").table(...)`, service-role key. CI already
  has `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `ANTHROPIC_API_KEY` as GitHub secrets.
  (Local dry runs used the Anthropic key from `TeamMembers/.env`.)

## Phase 1 — SHIPPED (2026-06-11)

1. ✅ First real `--write` run: source `707f09c4` + 6 ideas (5 ICP-voice / 1 proof), all
   `status='extracted'`. Required a migration (`allow_content_pulse_source_type`) extending the
   `content.sources.source_type` CHECK constraint with `'content_pulse'` — the "zero schema
   surgery" claim missed the CHECK constraint.
2. ✅ CI: `.github/workflows/content-pulse.yml` — Mondays 13:00 UTC, `--write` + slim email +
   Slack failure alert. `workflow_dispatch` input `email_only=true` skips generation (re-email
   an already-written run without double-writing).
3. ✅ Slim email: `send_content_pulse_email.py` — "N new angles this week → review in
   `/find-ideas`" via the `send-pulse-email` edge function.
4. Old Monday "OpenClaw Ecosystem Pulse" email left UNCHANGED — recalibration is a separate
   discussion (Robby, 2026-06-11). Known issues logged that day: 18/19 topics stuck at
   stage='inflection' (stage signal saturated); topic keyword-matching pulls generic GitHub
   repos into business topics.
5. Linear housekeeping: see BRI-100 + ICP-doc ticket.

---

| Version | Date | Type | Change |
|---|---|---|---|
| 0.5 | 2026-06-11 | Major | Email redesigned receipt → Monday POV briefing (through-line + owner quotes + lead angle teed up; /find-ideas reference dropped — skill doesn't exist yet, BRI-46/47). Hopeful-humanity philosophy promoted from seasoning to spine in synthesis prompt (Robby). Sources stay broad-SMB until proof says otherwise (Robby) |
| 0.4 | 2026-06-11 | Major | Phase 1 SHIPPED — real `--write` run (6 angles live), CHECK-constraint migration, CI workflow + slim email. Old email untouched pending recalibration discussion |
| 0.3 | 2026-06-04 | Major | Phase 1 BUILT + dry-run validated. ICP corrected agencies→SMBs; Moonshots-as-seasoning + SMB-only + pain-led decisions locked; source set + record shape + buckets taxonomy locked; files + remaining steps documented |
| 0.2 | 2026-06-02 | Major | Two-track frame; verified DB state; Signal clarified (reused); Linear project + BRI-100…105 |
| 0.1 | 2026-06-02 | Major | Initial capture — assessment + 4-phase rollout |
