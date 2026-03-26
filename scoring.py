"""Scoring engine — composite score calculation and stage classification.

Implements the Bridge Ninja intelligence scoring model:
- Weighted composite score (0-100) from 6 signal dimensions
- Stage classification: emergence -> traction -> inflection
- Hysteresis to prevent stage oscillation
- Cold-start fixed ranges for first 8 weeks

Weights and thresholds from DESIGN.md Section 4 and scoring-engine.md.
"""
from __future__ import annotations

# ── Fixed reference ranges (cold-start, weeks 0-8) ──────────────────
# Calibrated estimates based on the 15 starting topics.
# Replaced by empirical percentiles after 8+ weeks of data.

COLD_START_RANGES = {
    "github_star_delta": {"min": 0, "max": 500},
    "source_categories_seen": {"min": 0, "max": 6},
    "hn_combined": {"min": 0, "max": 200},
    "youtube_video_count": {"min": 0, "max": 20},
    "news_mention_count": {"min": 0, "max": 30},
    "github_fork_delta": {"min": 0, "max": 100},
}

# ── Signal weights (v1) ─────────────────────────────────────────────
# Total: 1.00. Cross-source validation is intentionally the heaviest.

WEIGHTS = {
    "github_star_delta": 0.20,
    "source_categories_seen": 0.25,
    "hn_combined": 0.15,
    "youtube_video_count": 0.15,
    "news_mention_count": 0.15,
    "github_fork_delta": 0.10,
}

# ── Stage classification rules ──────────────────────────────────────
# A topic is classified as the HIGHEST stage whose criteria it meets.

STAGE_RULES = {
    "inflection": {
        "composite_score_min": 65,
        "qualifiers": [
            {"signal": "github_star_delta", "op": ">=", "value": 500},
            {"signal": "source_categories_seen", "op": ">=", "value": 4},
            {"signal": "news_mention_count", "op": ">=", "value": 10},
            {"signal": "hn_max_points", "op": ">=", "value": 200},
            {"signal": "youtube_video_count", "op": ">=", "value": 10},
        ],
        "min_qualifiers": 2,
    },
    "traction": {
        "composite_score_min": 35,
        "qualifiers": [
            {"signal": "github_star_delta", "op": ">=", "value": 50},
            {"signal": "source_categories_seen", "op": ">=", "value": 3},
            {"signal": "hn_max_points", "op": ">=", "value": 50},
            {"signal": "youtube_video_count", "op": ">=", "value": 3},
            {"signal": "news_mention_count", "op": ">=", "value": 3},
        ],
        "min_qualifiers": 2,
    },
}

STAGE_ORDER = {"emergence": 0, "traction": 1, "inflection": 2}


# ── Normalization ────────────────────────────────────────────────────


def normalize(
    value: float | None,
    signal_key: str,
    history: list[float] | None = None,
) -> float:
    """Normalize a raw signal value to 0-100.

    If history has 8+ data points, use percentile normalization.
    Otherwise, use the cold-start fixed range.

    A None/null value returns 0.0 (missing signal = no contribution).
    """
    if value is None:
        return 0.0

    value = max(0.0, float(value))  # Floor at zero

    if history and len(history) >= 8:
        # Percentile normalization
        sorted_hist = sorted(history)
        rank = sum(1 for h in sorted_hist if h <= value)
        return round((rank / len(sorted_hist)) * 100, 2)
    else:
        # Cold-start: min-max against fixed range
        ref = COLD_START_RANGES.get(signal_key)
        if not ref:
            return 0.0
        if ref["max"] == ref["min"]:
            return 50.0
        normalized = (value - ref["min"]) / (ref["max"] - ref["min"])
        return round(min(max(normalized * 100, 0), 100), 2)


# ── HN Combined Signal ──────────────────────────────────────────────


def compute_hn_combined(
    hn_mentions: int | None, hn_max_points: int | None
) -> float:
    """Combine HN mentions and max points into a single signal.

    Formula: (mentions * 5) + max_points
    - 10 mentions = 50 base points
    - A front-page post (100+ points) doubles the signal
    """
    mentions = hn_mentions or 0
    max_pts = hn_max_points or 0
    return float((mentions * 5) + max_pts)


# ── Composite Score ──────────────────────────────────────────────────


def compute_composite_score(
    signals_summary: dict,
    history: dict[str, list[float]] | None = None,
) -> float:
    """Compute the weighted composite score (0-100) for a topic snapshot.

    Args:
        signals_summary: Raw signal values for this period.
            Expected keys: github_star_delta, source_categories_seen,
            hn_mentions, hn_max_points, youtube_video_count,
            news_mention_count, github_fork_delta
        history: Per-signal historical values for percentile normalization.
            Keys match signal_key names. Empty or None triggers cold-start.

    Returns:
        Composite score from 0.0 to 100.0.
    """
    if history is None:
        history = {}

    # Step 1: Compute derived signals
    hn_combined = compute_hn_combined(
        signals_summary.get("hn_mentions"),
        signals_summary.get("hn_max_points"),
    )

    # Step 2: Build signal map
    raw_signals = {
        "github_star_delta": signals_summary.get("github_star_delta"),
        "source_categories_seen": signals_summary.get("source_categories_seen"),
        "hn_combined": hn_combined,
        "youtube_video_count": signals_summary.get("youtube_video_count"),
        "news_mention_count": signals_summary.get("news_mention_count"),
        "github_fork_delta": signals_summary.get("github_fork_delta"),
    }

    # Step 3: Normalize each signal
    normalized = {}
    for key, raw_value in raw_signals.items():
        hist = history.get(key, [])
        normalized[key] = normalize(raw_value, key, hist)

    # Step 4: Apply weights (missing signals contribute 0, weight NOT redistributed)
    score = sum(WEIGHTS[key] * normalized[key] for key in WEIGHTS)

    return round(score, 2)


# ── Stage Classification ────────────────────────────────────────────


def classify_stage(composite_score: float, signals_summary: dict) -> str:
    """Classify a topic into a lifecycle stage based on score and qualifiers.

    Evaluates from highest stage (inflection) downward. Returns the first
    stage whose criteria are fully met. Falls back to 'emergence'.

    Args:
        composite_score: The computed composite score.
        signals_summary: Raw signal values (for qualifier checks).

    Returns:
        One of: 'emergence', 'traction', 'inflection'
    """
    for stage_name in ["inflection", "traction"]:
        rules = STAGE_RULES[stage_name]

        # Gate: composite score minimum
        if composite_score < rules["composite_score_min"]:
            continue

        # Count qualifying signals
        qualifiers_met = 0
        for q in rules["qualifiers"]:
            raw_value = signals_summary.get(q["signal"], 0) or 0
            if q["op"] == ">=" and raw_value >= q["value"]:
                qualifiers_met += 1

        if qualifiers_met >= rules["min_qualifiers"]:
            return stage_name

    return "emergence"


# ── Hysteresis ───────────────────────────────────────────────────────


def apply_stage_hysteresis(
    new_stage: str,
    current_stage: str,
    prior_stage_from_last_snapshot: str | None,
) -> str:
    """Apply hysteresis to prevent stage oscillation.

    Promotion: always immediate (one snapshot crossing threshold).
    Demotion: requires 2 consecutive below-threshold snapshots.

    Args:
        new_stage: Stage from classify_stage() for this snapshot.
        current_stage: The topic's current_stage in intelligence.topics.
        prior_stage_from_last_snapshot: Stage recorded in the previous snapshot.

    Returns:
        The final stage to assign.
    """
    new_rank = STAGE_ORDER.get(new_stage, 0)
    current_rank = STAGE_ORDER.get(current_stage, 0)

    # Promotion: always immediate
    if new_rank > current_rank:
        return new_stage

    # Same stage: no change
    if new_rank == current_rank:
        return current_stage

    # Demotion: only if prior snapshot ALSO suggested demotion
    if (
        prior_stage_from_last_snapshot
        and STAGE_ORDER.get(prior_stage_from_last_snapshot, 0) < current_rank
    ):
        return new_stage  # Second consecutive demotion signal — allow it

    # First demotion signal — hold at current stage
    return current_stage


# ── Score Delta ──────────────────────────────────────────────────────


def compute_score_delta(
    current_score: float, prior_snapshot: dict | None
) -> float:
    """Compute score change from the prior snapshot.

    Returns 0.0 for the first snapshot (no prior data).
    """
    if prior_snapshot is None:
        return 0.0
    prior_score = prior_snapshot.get("composite_score")
    if prior_score is None:
        return 0.0
    return round(current_score - prior_score, 2)


# ── Full Snapshot Scoring ────────────────────────────────────────────


def score_snapshot(
    topic: dict,
    signals_summary: dict,
    prior_snapshot: dict | None,
    history: dict[str, list[float]] | None = None,
) -> dict:
    """Full scoring pipeline for a single topic snapshot.

    Computes composite score, delta, stage classification with hysteresis.

    Args:
        topic: Topic row from intelligence.topics.
        signals_summary: Aggregated raw signal values for this collection window.
        prior_snapshot: Most recent prior snapshot (or None).
        history: Per-signal historical values for percentile normalization.

    Returns:
        Dict with composite_score, score_delta, stage, and all raw signals
        ready for snapshot upsert.
    """
    # Compute composite score
    composite_score = compute_composite_score(signals_summary, history)

    # Compute delta
    score_delta = compute_score_delta(composite_score, prior_snapshot)

    # Classify stage (raw, before hysteresis)
    classified_stage = classify_stage(composite_score, signals_summary)

    # Apply hysteresis
    current_stage = topic.get("current_stage", "emergence")
    prior_stage = prior_snapshot.get("stage") if prior_snapshot else None
    final_stage = apply_stage_hysteresis(
        new_stage=classified_stage,
        current_stage=current_stage,
        prior_stage_from_last_snapshot=prior_stage,
    )

    return {
        "composite_score": composite_score,
        "score_delta": score_delta,
        "stage": final_stage,
        "classified_stage_raw": classified_stage,  # Before hysteresis, for debugging
    }
