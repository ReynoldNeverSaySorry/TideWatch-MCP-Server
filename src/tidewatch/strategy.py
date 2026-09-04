"""Strategy semantics shared by signal generation, tracking, and review."""

from __future__ import annotations

from typing import Optional


OFFICIAL_STRATEGY_VERSION = "v4"
SHADOW_POLICY_VERSION = "v5.1-shadow"

BULLISH_DIRECTIONS = frozenset({"看多", "偏多"})
BEARISH_DIRECTIONS = frozenset({"看空", "偏空"})


def direction_outcome(direction: str, pct_change: float) -> str:
    """Evaluate the action the user actually saw, not the hidden score sign."""
    if direction in BULLISH_DIRECTIONS:
        return "correct" if pct_change > 0 else "wrong"
    if direction in BEARISH_DIRECTIONS:
        return "correct" if pct_change < 0 else "wrong"
    return "abstain"


def aligned_return(direction: str, pct_change: float) -> Optional[float]:
    """Return direction-aligned performance; abstentions have no trade return."""
    if direction in BULLISH_DIRECTIONS:
        return pct_change
    if direction in BEARISH_DIRECTIONS:
        return -pct_change
    return None


def v4_official_decision(
    adjusted_score: int,
    confidence: int,
    regime: str,
) -> tuple[str, list[str]]:
    """Return the current production direction and auditable decision tags."""
    if confidence < 40:
        tags = []
        if adjusted_score >= 50 or adjusted_score <= -25:
            tags.append("p0_confidence_downgrade")
        return "中性观望", tags
    if adjusted_score >= 50:
        if regime == "mild_bear":
            return "中性观望", ["mild_bear_bull_downgrade"]
        return "看多", []
    if adjusted_score >= 8:
        return "中性观望", ["weak_bull_abstain"]
    if adjusted_score <= -25:
        if regime == "mild_bull" and adjusted_score > -35:
            return "中性观望", ["mild_bull_bear_downgrade"]
        return "看空", []
    return "中性观望", ["weak_or_neutral_abstain"]


def v5_shadow_decision(
    official_direction: str,
    adjusted_score: int,
    confidence: int,
    regime: str,
) -> tuple[str, list[str]]:
    """Prospective v5 candidates; never changes the official v4 direction."""
    direction = official_direction
    tags: list[str] = []

    # New evidence: v4 P0 suppressed 20/23 correct weak bearish calls.
    if (
        official_direction == "中性观望"
        and confidence < 40
        and -40 < adjusted_score <= -25
        and regime != "bull"
    ):
        direction = "看空"
        tags.append("restore_weak_bear_non_bull")

    # Bull-regime directional calls were 7/21 correct after v4.
    if regime == "bull" and direction in BULLISH_DIRECTIONS | BEARISH_DIRECTIONS:
        direction = "中性观望"
        tags.append("bull_regime_abstain")

    return direction, tags


def should_record_shadow_scan(
    scan_ratio: float,
    market_data_date: Optional[str],
    expected_market_date: str,
) -> bool:
    """Fail closed when a daily scan is incomplete or stale."""
    return (
        scan_ratio >= 0.9
        and market_data_date is not None
        and market_data_date == expected_market_date
    )