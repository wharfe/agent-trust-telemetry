"""One-hop risk inheritance rule.

Implements parent_flagged_propagation: when a parent message was flagged
(warn/quarantine/block), the child message inherits a propagation signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from att.evaluator import Finding
from att.taxonomy import AnomalyIndicator, Severity


@dataclass
class InheritanceConfig:
    """Configuration for one-hop risk inheritance."""

    enabled: bool = True
    parent_action_threshold: list[str] | None = None
    propagated_confidence: float = 0.7
    # max_hops is defined for forward-compatibility with multi-hop inheritance
    # (Layer 3). MVP enforces one-hop only (ADR-002). The pipeline currently
    # performs a single parent lookup, so max_hops > 1 has no effect yet.
    max_hops: int = 1

    def __post_init__(self) -> None:
        if self.parent_action_threshold is None:
            self.parent_action_threshold = ["warn", "quarantine", "block"]


# Default configuration matching ADR-002
DEFAULT_CONFIG = InheritanceConfig()


def check_parent_propagation(
    parent_result: dict[str, Any] | None,
    config: InheritanceConfig | None = None,
) -> Finding | None:
    """Check if parent message triggers one-hop risk inheritance.

    Args:
        parent_result: The evaluation output of the parent message, or None.
        config: Inheritance configuration. Uses defaults if None.

    Returns:
        A Finding for parent_flagged_propagation if triggered, else None.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if not config.enabled:
        return None

    if parent_result is None:
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
