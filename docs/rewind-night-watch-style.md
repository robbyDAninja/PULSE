# Night Watch — the Rewind house style

**Version:** 1.0
**Last updated:** 2026-06-11

The design system for the Pulse **Rewind** series: single-file HTML data stories that replay a quarter of
the intelligence corpus as a narrative. Dark observatory aesthetic; honesty discipline is structural, not
decorative.

**Reference implementations:** `reports/rewind-ai-agent-security-2026-06-11.html` (№ 01),
`reports/rewind-ai-human-flourishing-2026-06-11.html` (№ 02). New volumes copy the newest file and replace
content; subtle variation per volume is allowed, sibling resemblance is required.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--ink` | `#0b1016` | background |
| `--paper` / `--paper-dim` / `--paper-faint` | `#e8ecef` / `#9aa7b1` / `#5c6b77` | text hierarchy |
| `--signal` | `#2fd4ad` | Bridge Ninja teal tuned for dark — the one accent |
| `--signal-deep` | `#16a085` | gradients only |
| `--ember` | `#f2b34c` | **reserved for the hope coda + HN tags** — never elsewhere |

Type: **Fraunces** (display), **Newsreader** (body, 19px/1.62), **IBM Plex Mono** (data, labels, dates).
Atmosphere: 56px graph-paper grid + radial teal glow + SVG fractal grain. Max width 1060px.

## Structure (fixed order)

1. **Masthead** — `Bridge Ninja · Intelligence` / pulsing dot / `Pulse · Rewind № NN`
2. **Hero** — mono eyebrow, Fraunces h1 with one italic teal `<em>`, standfirst, mono dateline, 4-stat strip
3. **Chart** — weekly signal volume bars (real counts, hover tips) + *honest footnote* on edge artifacts
4. **Chapters ×4** — timeline spine, month + week range, Fraunces h2, body (~5 sentences), **receipt cards**:
   real dated signals with source tag (RSS/HN/GITHUB) and traction only where real
5. **The Thread** — centered italic blockquote naming the quarter's arc, teal `.arc` span, ember kicker
6. **Coda** (amber-bordered) — "Why this matters — if you run a business" · ends "Grounded hope, with receipts."
7. **Colophon** — "Provenance & honesty": corpus size, window, sources, caveats stated plainly

Scroll-reveal via IntersectionObserver; bars animate on entry. No external JS/CSS beyond Google Fonts.

## Honesty rules (load-bearing — this is what makes it land)

- Every receipt is a real captured signal with its real date. Verify theme-fit per receipt; keyword noise is real.
- Titles-only corpus → "a headline says Goldman says," never restated as verified fact.
- Disclose the noise (the kimchi study, the 752-star ADHD repo). Include the cynical read when the corpus holds one.
- Don't inflate quiet topics — let the data's shape be the finding (№ 02's flat "worry hum").

## Build process

Query `intelligence.signals` ⋈ `intelligence.topics` by slug: weekly counts via
`date_trunc('week', discovered_at)`; top-10/week via `row_number() over (partition by week order by
points_or_stars desc)`. Points-ranked view is often noise — the story usually lives in the RSS headlines.
Verify rendering with headless Chrome CLI screenshots before shipping.

---

| Version | Date | Type | Change |
|---|---|---|---|
| 1.0 | 2026-06-11 | Major | Initial — codified from Rewind № 01–02 |
