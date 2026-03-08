"""Multi-hop risk inheritance rule.

Implements parent_flagged_propagation: when ancestor messages were flagged
(warn/quarantine/block), the descendant message inherits propagation signals
with confidence decaying per hop.

Layer 3 extension: supports multi-hop ancestor traversal via SessionStore.
When max_hops=1, behavior is backward-compatible with the original one-hop rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from att.evaluator import Finding
from att.taxonomy import AnomalyIndicator, Severity


@dataclass
class InheritanceConfig:
    """Configuration for multi-hop risk inheritance."""

    enabled: bool = True
    parent_action_threshold: list[str] | None = None
    propagated_confidence: float = 0.7
    max_hops: int = 3
    decay_per_hop: float = 0.15
    session_store: str = "memory"

    def __post_init__(self) -> None:
        if self.parent_action_threshold is None:
            self.parent_action_threshold = ["warn", "quarantine", "block"]
        # Clamp max_hops to valid range
        self.max_hops = max(1, min(10, self.max_hops))


# Default configuration (Layer 3 defaults)
DEFAULT_CONFIG = InheritanceConfig()


def calculate_propagated_confidence(
    hops: int,
    decay_per_hop: float = 0.15,
    base_confidence: float = 0.7,
) -> float:
    """Calculate confidence decayed by hop distance.

    At hops=1, returns base_confidence (0.7) for backward compatibility.
    Each additional hop reduces confidence by decay_per_hop.
    """
    return max(0.0, base_confidence - (hops - 1) * decay_per_hop)


def check_parent_propagation(
    parent_result: dict[str, Any] | None,
    config: InheritanceConfig | None = None,
) -> Finding | None:
    """Check if parent message triggers one-hop risk inheritance.

    This is the original single-parent API, preserved for backward compatibility.
    For multi-hop, use check_ancestor_propagation instead.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if not config.enabled or parent_result is None:
        return None

    parent_action = parent_result.get("recommended_action", "observe")
    assert config.parent_action_threshold is not None
    if parent_action not in config.parent_action_threshold:
        return None

    parent_id = parent_result.get("message_id", "unknown")
    parent_score = parent_result.get("risk_score", 0)

    return Finding(
        rule_id="__inheritance__",
        rule_description=(
            f"parent message {parent_id} was flagged "
            f"(risk_score: {parent_score}, action: {parent_action})"
        ),
        policy_class=None,
        anomaly_indicator=AnomalyIndicator.PROVENANCE_OR_METADATA_DRIFT.value,
        confidence=config.propagated_confidence,
        severity=Severity.HIGH.value,
        weight=1.0,
        matched_field="__parent_flagged_propagation__",
        matched_text="",
    )


@dataclass
class AncestorHit:
    """A flagged ancestor found during multi-hop traversal."""

    message_id: str
    hops: int
    risk_score: int
    action: str
    confidence: float


def check_ancestor_propagation(
    ancestors: list[dict[str, Any]],
    config: InheritanceConfig | None = None,
) -> list[Finding]:
    """Check multi-hop ancestor chain for risk propagation.

    Args:
        ancestors: List of ancestor results with '_hops' key, ordered nearest-first.
        config: Inheritance configuration.

    Returns:
        List of findings for each flagged ancestor, with decayed confidence.
        Only the highest-confidence finding is typically used by the scorer,
        but all are returned for evidence/audit purposes.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if not config.enabled or not ancestors:
        return []

    assert config.parent_action_threshold is not None
    findings: list[Finding] = []

    for ancestor in ancestors:
        action = ancestor.get("recommended_action", "observe")
        if action not in config.parent_action_threshold:
            continue

        hops = ancestor.get("_hops", 1)
        ancestor_id = ancestor.get("message_id", "unknown")
        ancestor_score = ancestor.get("risk_score", 0)

        confidence = calculate_propagated_confidence(
            hops=hops,
            decay_per_hop=config.decay_per_hop,
            base_confidence=config.propagated_confidence,
        )

        # Skip if confidence has decayed to zero
        if confidence <= 0.0:
            continue

        findings.append(Finding(
            rule_id="__inheritance__",
            rule_description=(
                f"ancestor message {ancestor_id} was flagged "
                f"(risk_score: {ancestor_score}, action: {action}, hops: {hops})"
            ),
            policy_class=None,
            anomaly_indicator=AnomalyIndicator.PROVENANCE_OR_METADATA_DRIFT.value,
            confidence=confidence,
            severity=Severity.HIGH.value,
            weight=1.0,
            matched_field="__parent_flagged_propagation__",
            matched_text="",
        ))

    return findings
