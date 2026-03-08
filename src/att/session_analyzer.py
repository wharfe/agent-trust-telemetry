"""Session-level analysis for Layer 3.

Implements:
- Role-transition drift detection
- History inconsistency detection (delegated to rule engine)
- Policy class accumulation bonus
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from att.evaluator import Finding
from att.taxonomy import AnomalyIndicator, Severity

# Default allowed role transitions
DEFAULT_ALLOWED_TRANSITIONS: list[dict[str, str]] = [
    {"from": "content", "to": "tool_call"},
    {"from": "tool_call", "to": "content"},
    {"from": "content", "to": "content"},
    {"from": "tool_call", "to": "tool_call"},
    {"from": "system", "to": "system"},
    {"from": "unknown", "to": "content"},
    {"from": "unknown", "to": "tool_call"},
    {"from": "unknown", "to": "unknown"},
]


@dataclass
class SessionAnalyzerConfig:
    """Configuration for session-level analysis."""

    role_transition_enabled: bool = True
    accumulation_enabled: bool = True
    allowed_role_transitions: list[dict[str, str]] = field(
        default_factory=lambda: list(DEFAULT_ALLOWED_TRANSITIONS)
    )
    role_transition_confidence: float = 0.80
    role_transition_severity: str = Severity.MEDIUM.value


class SessionAnalyzer:
    """Tracks session-level state for Layer 3 analysis.

    Maintains per-session, per-sender role history and per-session
    policy class accumulation.
    """

    def __init__(self, config: SessionAnalyzerConfig | None = None) -> None:
        self._config = config or SessionAnalyzerConfig()
        # session_id -> sender -> list of roles seen (in order)
        self._role_history: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # session_id -> set of detected policy classes
        self._session_classes: dict[str, set[str]] = defaultdict(set)

    def analyze(
        self,
        envelope: dict[str, Any],
        current_findings: list[Finding],
    ) -> list[Finding]:
        """Run session-level analysis on the current message.

        Args:
            envelope: The message envelope being evaluated.
            current_findings: Findings from Layer 1 and inheritance.

        Returns:
            Additional findings from session analysis.
        """
        session_id = envelope.get("session_id", "")
        sender = envelope.get("sender", "")
        role = envelope.get("role", "unknown")

        new_findings: list[Finding] = []

        # Role-transition drift
        if self._config.role_transition_enabled and sender:
            drift = self._check_role_transition(session_id, sender, role)
            if drift is not None:
                new_findings.append(drift)

        # Track role history (after check, so we compare against previous)
        if sender:
            self._role_history[session_id][sender].append(role)

        # Accumulate policy classes from current findings
        for f in current_findings:
            if f.policy_class and f.confidence >= 0.5:
                self._session_classes[session_id].add(f.policy_class)

        return new_findings

    def get_distinct_policy_classes(self, session_id: str) -> set[str]:
        """Return set of distinct policy classes detected in session."""
        return self._session_classes.get(session_id, set())

    def calculate_session_bonus(
        self,
        session_id: str,
        current_risk_score: int,
    ) -> int:
        """Apply session accumulation bonus to risk score.

        Each additional distinct policy class in the session adds +5,
        capped at +15.
        """
        if not self._config.accumulation_enabled:
            return current_risk_score

        distinct_count = len(self._session_classes.get(session_id, set()))
        if distinct_count <= 1:
            return current_risk_score

        bonus = min(15, (distinct_count - 1) * 5)
        return min(100, current_risk_score + bonus)

    def _check_role_transition(
        self,
        session_id: str,
        sender: str,
        current_role: str,
    ) -> Finding | None:
        """Check if the role transition is allowed."""
        history = self._role_history[session_id][sender]
        if not history:
            return None  # First message from this sender, no transition to check

        previous_role = history[-1]
        if previous_role == current_role:
            return None  # Same role, no transition

        # Check if this transition is allowed
        allowed = self._config.allowed_role_transitions
        for rule in allowed:
            if rule["from"] == previous_role and rule["to"] == current_role:
                return None

        return Finding(
            rule_id="__role_transition_drift__",
            rule_description=(
                f"sender '{sender}' transitioned from role '{previous_role}' "
                f"to '{current_role}' (not in allowed transitions)"
            ),
            policy_class=None,
            anomaly_indicator=AnomalyIndicator.PROVENANCE_OR_METADATA_DRIFT.value,
            confidence=self._config.role_transition_confidence,
            severity=self._config.role_transition_severity,
            weight=1.0,
            matched_field="__role_transition_drift__",
            matched_text=f"{previous_role} -> {current_role}",
        )

    def get_role_transitions(
        self, session_id: str
    ) -> list[dict[str, Any]]:
        """Return all role transitions for a session, with flagged status."""
        transitions: list[dict[str, Any]] = []
        allowed = self._config.allowed_role_transitions

        for sender, roles in self._role_history.get(session_id, {}).items():
            for i in range(1, len(roles)):
                prev_role = roles[i - 1]
                curr_role = roles[i]
                if prev_role == curr_role:
                    continue
                is_allowed = any(
                    r["from"] == prev_role and r["to"] == curr_role
                    for r in allowed
                )
                transitions.append({
                    "sender": sender,
                    "from": prev_role,
                    "to": curr_role,
                    "flagged": not is_allowed,
                })
        return transitions

    def clear(self, session_id: str | None = None) -> None:
        """Clear session analysis state."""
        if session_id is not None:
            self._role_history.pop(session_id, None)
            self._session_classes.pop(session_id, None)
        else:
            self._role_history.clear()
            self._session_classes.clear()
