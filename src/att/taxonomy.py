"""Policy violation taxonomy definitions.

Defines the two-layer taxonomy: policy violation classes (behavioral)
and anomaly indicators (expression patterns).
"""

from enum import Enum


class PolicyClass(str, Enum):
    """Policy violation classes — behavioral categories of violations."""

    INSTRUCTION_OVERRIDE = "instruction_override"
    PRIVILEGE_ESCALATION_ATTEMPT = "privilege_escalation_attempt"
    SECRET_ACCESS_ATTEMPT = "secret_access_attempt"
    EXFILTRATION_ATTEMPT = "exfiltration_attempt"
    TOOL_MISUSE_ATTEMPT = "tool_misuse_attempt"


class AnomalyIndicator(str, Enum):
    """Anomaly indicators — expression patterns of attacks."""

    HIDDEN_INSTRUCTION_EMBEDDING = "hidden_instruction_embedding"
    PROVENANCE_OR_METADATA_DRIFT = "provenance_or_metadata_drift"


class ProvenanceSubclass(str, Enum):
    """Subclasses of provenance_or_metadata_drift."""

    TOOL_METADATA_DRIFT = "tool_metadata_drift"
    PARENT_FLAGGED_PROPAGATION = "parent_flagged_propagation"
    # Out of scope for MVP:
    # DECLARED_PROVENANCE_MISMATCH = "declared_provenance_mismatch"
    # CAPABILITY_PROVENANCE_MISMATCH = "capability_provenance_mismatch"
    # INSTRUCTION_LINEAGE_MISMATCH = "instruction_lineage_mismatch"


class Severity(str, Enum):
    """Severity levels ordered by impact."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @staticmethod
    def _order() -> dict[str, int]:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order()[self.value] >= self._order()[other.value]

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order()[self.value] > self._order()[other.value]

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order()[self.value] <= self._order()[other.value]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order()[self.value] < self._order()[other.value]


class Action(str, Enum):
    """Recommended response actions."""

    OBSERVE = "observe"
    WARN = "warn"
    QUARANTINE = "quarantine"
    BLOCK = "block"


# Priority classification for action decision rules
P0_CLASSES: set[str] = {
    PolicyClass.INSTRUCTION_OVERRIDE,
    PolicyClass.PRIVILEGE_ESCALATION_ATTEMPT,
    PolicyClass.SECRET_ACCESS_ATTEMPT,
    AnomalyIndicator.HIDDEN_INSTRUCTION_EMBEDDING,
}

P1_CLASSES: set[str] = {
    PolicyClass.EXFILTRATION_ATTEMPT,
    PolicyClass.TOOL_MISUSE_ATTEMPT,
    AnomalyIndicator.PROVENANCE_OR_METADATA_DRIFT,
}
