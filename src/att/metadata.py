"""Tool metadata drift tracking.

Tracks description_hash per {sender}:{tool_name} within a session
and detects changes (tool_metadata_drift).
"""

from __future__ import annotations

from att.evaluator import Finding
from att.taxonomy import AnomalyIndicator, Severity


class MetadataTracker:
    """Session-scoped tracker for tool description hash changes."""

    def __init__(self) -> None:
        # Key: "{sender}:{tool_name}", Value: last seen description_hash
        self._hashes: dict[str, str] = {}

    def check(
        self,
        session_id: str,
        sender: str,
        tool_name: str | None,
        description_hash: str | None,
    ) -> Finding | None:
        """Check for tool_metadata_drift.

        Returns a Finding if the description_hash has changed for the same
        {sender}:{tool_name} combination within the session.
        Returns None on first observation or if tool_name/hash is absent.
        """
        if tool_name is None or description_hash is None:
            return None

        key = f"{session_id}:{sender}:{tool_name}"
        previous = self._hashes.get(key)
        self._hashes[key] = description_hash

        if previous is None:
            # First observation — record and return
            return None

        if previous == description_hash:
            # No change
            return None

        return Finding(
            rule_id="__tool_metadata_drift__",
            rule_description=(
                f"tool description hash changed for {sender}:{tool_name} "
                f"(previous: {previous[:20]}..., current: {description_hash[:20]}...)"
            ),
            policy_class=None,
            anomaly_indicator=AnomalyIndicator.PROVENANCE_OR_METADATA_DRIFT.value,
            confidence=0.85,
            severity=Severity.HIGH.value,
            weight=1.0,
            matched_field="__tool_metadata_drift__",
            matched_text="",
        )

    def clear(self) -> None:
        """Clear all tracked hashes."""
        self._hashes.clear()
