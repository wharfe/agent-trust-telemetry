"""Evaluation pipeline — full evaluation flow with Layer 3 session analysis.

Provides a high-level API for evaluating messages with full context.
Layer 3: adds SessionStore for multi-hop inheritance and SessionAnalyzer
for role-transition drift, history inconsistency, and policy class accumulation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from att.evaluator import Finding, evaluate_message, load_rules
from att.inheritance import (
    InheritanceConfig,
    check_ancestor_propagation,
    check_parent_propagation,
)
from att.metadata import MetadataTracker
from att.scorer import ScoringResult, score
from att.session_analyzer import SessionAnalyzer, SessionAnalyzerConfig
from att.session_store import InMemorySessionStore, SessionStore

DEFAULT_RULES_DIR = Path(__file__).resolve().parent / "rules" / "builtin"


class EvaluationPipeline:
    """Full evaluation pipeline for message envelopes.

    Combines Layer 1 rule evaluation, tool metadata drift tracking,
    multi-hop parent risk inheritance, and session-level analysis
    into a single evaluation flow.
    """

    def __init__(
        self,
        rules_dir: Path | None = None,
        inheritance_config: InheritanceConfig | None = None,
        session_analyzer_config: SessionAnalyzerConfig | None = None,
        session_store: SessionStore | None = None,
        otel_enabled: bool = False,
    ) -> None:
        self._rules = load_rules(rules_dir or DEFAULT_RULES_DIR)
        self._inheritance_config = inheritance_config or InheritanceConfig()
        self._metadata_tracker = MetadataTracker()
        self._session_analyzer = SessionAnalyzer(session_analyzer_config)
        self._session_store: SessionStore = session_store or InMemorySessionStore()
        self._otel_enabled = otel_enabled
        # Legacy cache for backward compat when max_hops=1
        self._results_cache: dict[str, dict[str, Any]] = {}

    def evaluate(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single message envelope.

        Uses SessionStore for multi-hop ancestor lookups when max_hops > 1.
        Falls back to legacy single-parent cache when max_hops = 1.

        Returns the output contract dict.
        """
        if not isinstance(envelope, dict):
            raise TypeError(
                f"envelope must be a dict, got {type(envelope).__name__}"
            )

        session_id = envelope.get("session_id", "")
        message_id = envelope.get("message_id", "")
        parent_id = envelope.get("parent_message_id")

        # Layer 1: pattern matching
        findings: list[Finding] = evaluate_message(envelope, self._rules)

        # Tool metadata drift check
        raw_tool_ctx = envelope.get("tool_context")
        tool_ctx = raw_tool_ctx if isinstance(raw_tool_ctx, dict) else {}
        drift_finding = self._metadata_tracker.check(
            session_id=session_id,
            sender=envelope.get("sender", ""),
            tool_name=tool_ctx.get("tool_name"),
            description_hash=tool_ctx.get("description_hash"),
        )
        if drift_finding is not None:
            findings.append(drift_finding)

        # Multi-hop or one-hop inheritance
        max_hops = self._inheritance_config.max_hops
        if parent_id is not None:
            if max_hops > 1:
                # Multi-hop: use SessionStore to walk ancestor chain
                ancestors = self._session_store.get_ancestors(
                    session_id, message_id, max_hops,
                    parent_message_id=parent_id,
                )
                ancestor_findings = check_ancestor_propagation(
                    ancestors, self._inheritance_config
                )
                findings.extend(ancestor_findings)
            else:
                # One-hop: legacy behavior
                parent_result = self._results_cache.get(parent_id)
                inheritance_finding = check_parent_propagation(
                    parent_result, self._inheritance_config
                )
                if inheritance_finding is not None:
                    findings.append(inheritance_finding)

        # Session-level analysis (role transition drift, accumulation)
        # Only active when Layer 3 is enabled (max_hops > 1)
        if max_hops > 1:
            session_findings = self._session_analyzer.analyze(envelope, findings)
            findings.extend(session_findings)

        # Scoring
        result: ScoringResult = score(findings)

        # Apply session accumulation bonus (Layer 3 only)
        if max_hops > 1:
            risk_score = self._session_analyzer.calculate_session_bonus(
                session_id, result.risk_score
            )
        else:
            risk_score = result.risk_score

        # Build output contract
        output: dict[str, Any] = {
            "schema_version": "0.2" if max_hops > 1 else "0.1",
            "message_id": message_id,
            "trace_id": envelope.get("trace_id", ""),
            "session_id": session_id,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "risk_score": risk_score,
            "severity": result.severity,
            "policy_classes": result.policy_classes,
            "anomaly_indicators": result.anomaly_indicators,
            "evidence": result.evidence,
            "recommended_action": result.recommended_action,
        }

        # Add session_context for Layer 3
        if max_hops > 1:
            flagged_ancestors = []
            if parent_id is not None:
                ancestors = self._session_store.get_ancestors(
                    session_id, message_id, max_hops,
                    parent_message_id=parent_id,
                )
                for a in ancestors:
                    a_action = a.get("recommended_action", "observe")
                    if a_action in (self._inheritance_config.parent_action_threshold or []):
                        flagged_ancestors.append({
                            "message_id": a.get("message_id", ""),
                            "hops": a.get("_hops", 1),
                            "risk_score": a.get("risk_score", 0),
                        })

            output["session_context"] = {
                "session_risk_score": risk_score,
                "distinct_policy_classes": len(
                    self._session_analyzer.get_distinct_policy_classes(session_id)
                ),
                "flagged_ancestors": flagged_ancestors,
                "role_transitions": self._session_analyzer.get_role_transitions(
                    session_id
                ),
            }

        # OTel export (optional)
        if self._otel_enabled:
            from att.exporters.otel import export_evaluation

            export_evaluation(output)

        # Store result for future lookups
        # Include parent_message_id for ancestor chain traversal
        output_with_parent = dict(output)
        output_with_parent["_parent_message_id"] = parent_id
        self._session_store.put(session_id, output_with_parent)

        # Legacy cache for one-hop backward compat
        self._results_cache[message_id] = output
        return output

    def reset(self) -> None:
        """Reset internal state (metadata tracker, results cache, session state)."""
        self._metadata_tracker.clear()
        self._results_cache.clear()
        self._session_store.clear()
        self._session_analyzer.clear()
