# Bridge Ninja Pulse

**Version:** 2.0
**Last updated:** 2026-10-07

Pulse has two separate research tracks. The practical publishing track helps
local business owners use AI for useful video, consistent social content and
repeatable work. The broad intelligence collector and historical OpenClaw
reports retain their own configuration. A configured workflow does not prove
current collection, subscriber delivery or publication.

## Practical publishing research

[`content_pulse.config.yml`](content_pulse.config.yml) sets five research areas:

| Area | Useful question |
|---|---|
| Owner needs | What customer or communication task needs attention? |
| Video and avatars | What improves usable speech, likeness, consent and delivery? |
| Social workflows | How can an owner plan, approve, publish and learn consistently? |
| Content economics | What is the total cost of equivalent accepted work? |
| Future capabilities | What broader development deserves watching? At most one candidate. |

The initial local area is Florida's Treasure Coast, an explicit working
assumption. Chamber pages provide context. Community posts provide question
leads. Neither proves local buying intent. Record direct owner feedback in
private intake; vendor material remains commercially interested evidence.

Each packet contains zero to five candidates, with an owner problem, useful
takeaway, demonstration, honest service connection, source references, evidence
state, unresolved checks and a try/watch/skip recommendation. No filler quota.

"Are you overpaying for social content?" can be a research question. A savings
assertion needs observed total costs for comparable deliverables, quality,
revisions, posting responsibility, labor and allocated subscriptions. Tool plan
prices alone cannot establish service savings. Validation checks packet
structure and evidence references; human review still establishes truth.

## Private preparation commands

Use Python 3.9 or newer and `pip install -r requirements.txt`. This repository is
public. Actual intake, source snapshots, model receipts and review packets must
live **outside** it. The commands reject in-repository output, including paths
through symlinks. `.gitignore` is an additional guard, not a privacy boundary.

```bash
# Fetch only: no model call, database writes, email, or publication.
python generate_content_pulse.py fetch --public-only \
  --out /private/path/sources-public.json

# Full private intake. See the fictional schema example below.
python generate_content_pulse.py fetch --intake /private/path/intake.json \
  --out /private/path/sources.json

# Optional paid synthesis, only within separately approved budget and input scope.
# Token count and the configured maximum output determine an estimated ceiling.
python generate_content_pulse.py synthesize --input /private/path/sources.json \
  --out /private/path/proposal.json --receipt-out /private/path/model-attempt.json \
  --budget-usd APPROVED_AMOUNT

# A human can prepare proposal JSON instead, with no model call.
python generate_content_pulse.py validate --input /private/path/proposal.json \
  --sources /private/path/sources.json --out /private/path/validated.json
python generate_content_pulse.py render-packet --input /private/path/proposal.json \
  --sources /private/path/sources.json --out /private/path/review.html
```

The default command is `fetch`; default output is under
`~/.local/state/bridge-ninja/practical-pulse/`. Real local intake is required
before synthesis/validation. `--public-only` is a source rehearsal: missing
private intake stays visible, so its success is not an editorial-ready packet.
Use the exact captured configuration to validate its snapshot.

Private intake is manually sourced, not automated outreach or customer
surveillance. This **fictional** example shows the schema; actual records belong
outside this repository:

```json
{
  "schema_version": "2.0",
  "items": [{
    "record_id": "fictional-owner-question-1",
    "title": "How should I approve a content batch?",
    "excerpt": "Fictional schema illustration, not actual owner evidence.",
    "source_locator": "Fictional example only",
    "observed_at": "2026-10-07T12:00:00Z",
    "lane": "owner_needs",
    "role": "research_hypothesis",
    "visibility": "internal",
    "publication_permission": "not_granted"
  }]
}
```

Supported intake roles are `local_owner_question`, `internal_observation` and
`research_hypothesis`. A client request, proposed package, actual production
observation and measured result are different evidence states. Private research
input is not authority for a public case study or a new client service.

RSS dates are normalized to UTC and filtered to the seven-day window. Unknown
dates are reference-only. Page/changelog retrieval never creates a publication
date: inspect a dated individual announcement before calling something new.
Snapshots retain hashes and source-health states; failed fetches are distinct
from healthy feeds with no current entries. Blocked/login-required sources need
authorized manual checking. Do not bypass them or fill gaps with guesses.

Paid synthesis has no automatic retry. A transport failure leaves an
`attempt_started_outcome_unknown` receipt. Reconcile that attempt before any
retry; changing the receipt filename is not permission to repeat it. Model
rates expire for this purpose after 30 days. Current configured rates were
checked against [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).

The renderer labels output private and unapproved. Robby editorial selection,
demonstrations, factual checks, issue creation, Robby approval and Raegen final
release remain downstream steps. This module never writes Supabase, sends the
legacy briefing, uploads client media, or sends newsletters.

## Rehearsal, monitoring and activation

```bash
python -m unittest discover -s tests -v
```

The Content Pulse workflow is manual, read-only source preparation. It runs the
tests and fetches public sources into temporary runner storage, without a model
key or uploaded artifact. Logs expose counts/source failures, not raw packets.
It is not the private editorial destination or a weekly monitor.

Before recurring activation, the launch workplan must settle the weekly time,
private destination, input authority, model budget, operator and independent
missed-run check. That check must catch a silent/disabled workflow and inspect
freshness, source coverage and the actual packet. Job success alone is not
enough. Subscriber release belongs to the separately approved publishing path.

## Broad and historical tracks

`collect_signals.py`, `generate_briefing.py` and their workflow retain the broad
intelligence track. `config.yml`, `generate_pulse.py` and `reports/` retain the
historical OpenClaw track. Practical feed changes do not reactivate or rewrite
those tracks. Inspect GitHub's current workflow state before asserting any
schedule is running.

## Changelog

| Version | Date | Change |
|---|---|---|
| 2.0 | 2026-10-07 | Documented practical local-business research, separate private stages, evidence rules, bounded synthesis and activation requirements; retained broad/historical tracks. |
