"""Evaluation pipeline — ties together evaluator, inheritance, metadata, and scorer.

Provides a high-level API for evaluating messages with full context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from att.evaluator import Finding, evaluate_message, load_rules
from att.inheritance import InheritanceConfig, check_parent_propagation
from att.metadata import MetadataTracker
from att.scorer import ScoringResult, score

DEFAULT_RULES_DIR = Path(__file__).resolve().parents[2] / "rules" / "builtin"


class EvaluationPipeline:
    """Full evaluation pipeline for message envelopes.

    Combines Layer 1 rule evaluation, tool metadata drift tracking,
    and one-hop parent risk inheritance into a single evaluation flow.
    """

    def __init__(
        self,
        rules_dir: Path | None = None,
        inheritance_config: InheritanceConfig | None = None,
        otel_enabled: bool = False,
    ) -> None:
        self._rules = load_rules(rules_dir or DEFAULT_RULES_DIR)
        self._inheritance_config = inheritance_config or InheritanceConfig()
        self._metadata_tracker = MetadataTracker()
        self._otel_enabled = otel_enabled
        # Cache of message_id -> evaluation output for parent lookups
        self._results_cache: dict[str, dict[str, Any]] = {}

    def evaluate(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single message envelope.

        Looks up parent result from cache if parent_message_id is present.
        Stores result in cache for downstream child lookups.

        Returns the output contract dict.
        """
        # Layer 1: pattern matching
        findings: list[Finding] = evaluate_message(envelope, self._rules)

        # Tool metadata drift check
        tool_ctx = envelope.get("tool_context") or {}
        drift_finding = self._metadata_tracker.check(
            session_id=envelope.get("session_id", ""),
            sender=envelope.get("sender", ""),
            tool_name=tool_ctx.get("tool_name"),
            description_hash=tool_ctx.get("description_hash"),
        )
        if drift_finding is not None:
            findings.append(drift_finding)

        # One-hop inheritance
        parent_id = envelope.get("parent_message_id")
        if parent_id is not None:
            parent_result = self._results_cache.get(parent_id)
            inheritance_finding = check_parent_propagation(
                parent_result, self._inheritance_config
            )
            if inheritance_finding is not None:
                findings.append(inheritance_finding)

        # Scoring
        result: ScoringResult = score(findings)

        # Build output contract
        message_id = envelope.get("message_id", "")
        output: dict[str, Any] = {
            "schema_version": "0.1",
            "message_id": message_id,
            "trace_id": envelope.get("trace_id", ""),
            "session_id": envelope.get("session_id", ""),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "risk_score": result.risk_score,
            "severity": result.severity,
            "policy_classes": result.policy_classes,
            "anomaly_indicators": result.anomaly_indicators,
            "evidence": result.evidence,
            "recommended_action": result.recommended_action,
        }

        # OTel export (optional)
        if self._otel_enabled:
            from att.exporters.otel import export_evaluation

            export_evaluation(output)

        # Cache for parent lookups
        self._results_cache[message_id] = output
        return output

    def reset(self) -> None:
        """Reset internal state (metadata tracker and results cache)."""
        self._metadata_tracker.clear()
        self._results_cache.clear()
