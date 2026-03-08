"""Risk scoring and action recommendation engine.

Implements the scoring algorithm and recommended_action decision rules
defined in the MVP requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from att.evaluator import Finding
from att.taxonomy import (
    P0_CLASSES,
    Action,
    ProvenanceSubclass,
    Severity,
)

SEVERITY_ORDER = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


@dataclass
class ScoringResult:
    """Result of risk scoring and action determination."""

    risk_score: int
    severity: str
    recommended_action: str
    policy_classes: list[dict[str, Any]]
    anomaly_indicators: list[dict[str, Any]]
    evidence: list[str]


def _deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Deduplicate findings by class, keeping highest confidence per class."""
    best: dict[str, Finding] = {}
    for f in findings:
        cls = f.finding_class
        if cls not in best or f.confidence > best[cls].confidence:
            best[cls] = f
    return list(best.values())


def _compute_risk_score(findings: list[Finding]) -> int:
    """Compute risk_score from deduplicated findings.

    base  = max(f.confidence * f.weight for f in findings)
    bonus = min(0.2, 0.05 * (len(findings) - 1))
    risk_score = min(100, round((base + bonus) * 100))
    """
    if not findings:
        return 0

    deduped = _deduplicate_findings(findings)
    if not deduped:
        return 0

    base = max(f.confidence * f.weight for f in deduped)
    bonus = min(0.2, 0.05 * (len(deduped) - 1))
    return min(100, round((base + bonus) * 100))


def _compute_severity(findings: list[Finding]) -> str:
    """Compute overall severity as max of all finding severities."""
    if not findings:
        return Severity.LOW.value

    max_sev = Severity.LOW
    for f in findings:
        try:
            sev = Severity(f.severity)
        except ValueError:
            continue
        if sev > max_sev:
            max_sev = sev
    return max_sev.value


def _determine_action(findings: list[Finding]) -> str:
    """Determine recommended_action using the decision rules.

    Pre-filter: confidence < 0.5 findings are excluded.

    1. P0 + severity=critical                                     → block
    2. P0 + severity=high  OR  parent_flagged_propagation ≥ 0.5  → quarantine
    3. P0/P1 + severity < high                                    → warn
    4. No findings or all below threshold                          → observe
    """
    # Pre-filter
    active = [f for f in findings if f.confidence >= 0.5]
    if not active:
        return Action.OBSERVE.value

    for f in active:
        cls = f.finding_class
        sev = f.severity

        # Rule 1: P0 + critical → block
        if cls in P0_CLASSES and sev == Severity.CRITICAL.value:
            return Action.BLOCK.value

    for f in active:
        cls = f.finding_class
        sev = f.severity

        # Rule 2a: P0 + high → quarantine
        if cls in P0_CLASSES and sev == Severity.HIGH.value:
            return Action.QUARANTINE.value

        # Rule 2b: parent_flagged_propagation with confidence >= 0.5 → quarantine
        if (
            f.anomaly_indicator == "provenance_or_metadata_drift"
            and hasattr(f, "subclass")
        ):
            pass  # subclass check handled below

    # Check parent_flagged_propagation specifically
    for f in active:
        if (
            f.rule_id == "__inheritance__"
            or (
                f.anomaly_indicator == "provenance_or_metadata_drift"
                and f.matched_field == "__parent_flagged_propagation__"
            )
        ):
            return Action.QUARANTINE.value

    # Rule 3: any P0/P1 match with severity < high → warn
    if active:
        return Action.WARN.value

    return Action.OBSERVE.value


def _build_evidence(findings: list[Finding]) -> list[str]:
    """Build human-readable evidence strings from findings."""
    evidence: list[str] = []
    for f in findings:
        if f.confidence < 0.5:
            continue
        if f.matched_field == "__parent_flagged_propagation__":
            evidence.append(f.rule_description)
        else:
            evidence.append(
                f"{f.rule_description} (matched '{f.matched_text}' in {f.matched_field})"
            )
    return evidence


def _build_policy_classes(findings: list[Finding]) -> list[dict[str, Any]]:
    """Build policy_classes array for output contract."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in findings:
        if f.policy_class and f.policy_class not in seen:
            seen.add(f.policy_class)
            result.append({
                "name": f.policy_class,
                "confidence": f.confidence,
                "severity": f.severity,
            })
    return result


def _build_anomaly_indicators(findings: list[Finding]) -> list[dict[str, Any]]:
    """Build anomaly_indicators array for output contract."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in findings:
        if f.anomaly_indicator:
            key = f"{f.anomaly_indicator}:{f.matched_field}"
            if key not in seen:
                seen.add(key)
                subclass = None
                if f.matched_field == "__parent_flagged_propagation__":
                    subclass = ProvenanceSubclass.PARENT_FLAGGED_PROPAGATION.value
                elif f.matched_field == "__tool_metadata_drift__":
                    subclass = ProvenanceSubclass.TOOL_METADATA_DRIFT.value
                elif f.matched_field == "__role_transition_drift__":
                    subclass = ProvenanceSubclass.ROLE_TRANSITION_DRIFT.value
                elif (
                    f.anomaly_indicator == "provenance_or_metadata_drift"
                    and f.rule_id.startswith("rule:history_inconsistency")
                ):
                    subclass = ProvenanceSubclass.HISTORY_INCONSISTENCY.value
                entry: dict[str, Any] = {
                    "name": f.anomaly_indicator,
                    "confidence": f.confidence,
                    "severity": f.severity,
                }
                if subclass is not None:
                    entry["subclass"] = subclass
                else:
                    entry["subclass"] = None
                result.append(entry)
    return result


def score(findings: list[Finding]) -> ScoringResult:
    """Compute full scoring result from evaluation findings."""
    risk_score = _compute_risk_score(findings)
    severity = _compute_severity(findings)
    recommended_action = _determine_action(findings)
    policy_classes = _build_policy_classes(findings)
    anomaly_indicators = _build_anomaly_indicators(findings)
    evidence = _build_evidence(findings)

    return ScoringResult(
        risk_score=risk_score,
        severity=severity,
        recommended_action=recommended_action,
        policy_classes=policy_classes,
        anomaly_indicators=anomaly_indicators,
        evidence=evidence,
    )
