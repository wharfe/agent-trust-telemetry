"""OpenTelemetry export for trust evaluation results.

Adds security semantics to existing OTel traces by:
- Setting span attributes with trust evaluation summary
- Recording evaluation results as span events

Compatible with any OTel exporter (OTLP/gRPC, OTLP/HTTP, etc.).
"""

from __future__ import annotations

import json
from typing import Any

from opentelemetry import trace

# Span attribute keys
ATTR_RISK_SCORE = "trust.risk_score"
ATTR_SEVERITY = "trust.severity"
ATTR_RECOMMENDED_ACTION = "trust.recommended_action"
ATTR_POLICY_CLASSES = "trust.policy_classes"
ATTR_ANOMALY_INDICATORS = "trust.anomaly_indicators"

# Event name
EVENT_EVALUATION_COMPLETED = "trust.evaluation.completed"


def set_span_attributes(span: trace.Span, result: dict[str, Any]) -> None:
    """Set trust evaluation attributes on an OTel span.

    Args:
        span: The active OTel span to annotate.
        result: Evaluation output contract dict.
    """
    span.set_attribute(ATTR_RISK_SCORE, result.get("risk_score", 0))
    span.set_attribute(ATTR_SEVERITY, result.get("severity", "low"))
    span.set_attribute(
        ATTR_RECOMMENDED_ACTION, result.get("recommended_action", "observe")
    )
    span.set_attribute(
        ATTR_POLICY_CLASSES,
        json.dumps(result.get("policy_classes", []), ensure_ascii=False),
    )
    span.set_attribute(
        ATTR_ANOMALY_INDICATORS,
        json.dumps(result.get("anomaly_indicators", []), ensure_ascii=False),
    )


def record_evaluation_event(span: trace.Span, result: dict[str, Any]) -> None:
    """Record a trust evaluation as an OTel span event.

    The event contains the full output contract as attributes.
    After recording, trace_refs are populated in the result dict.

    Args:
        span: The active OTel span.
        result: Evaluation output contract dict (modified in-place with trace_refs).
    """
    # Build event attributes from the output contract
    event_attrs: dict[str, str | int] = {
        "trust.schema_version": result.get("schema_version", "0.1"),
        "trust.message_id": result.get("message_id", ""),
        "trust.trace_id": result.get("trace_id", ""),
        "trust.session_id": result.get("session_id", ""),
        "trust.evaluated_at": result.get("evaluated_at", ""),
        "trust.risk_score": result.get("risk_score", 0),
        "trust.severity": result.get("severity", "low"),
        "trust.recommended_action": result.get("recommended_action", "observe"),
        "trust.policy_classes": json.dumps(
            result.get("policy_classes", []), ensure_ascii=False
        ),
        "trust.anomaly_indicators": json.dumps(
            result.get("anomaly_indicators", []), ensure_ascii=False
        ),
        "trust.evidence": json.dumps(
            result.get("evidence", []), ensure_ascii=False
        ),
    }

    span.add_event(EVENT_EVALUATION_COMPLETED, attributes=event_attrs)

    # Populate trace_refs with span context info
    span_ctx = span.get_span_context()
    if span_ctx and span_ctx.is_valid:
        trace_id_hex = format(span_ctx.trace_id, "032x")
        span_id_hex = format(span_ctx.span_id, "016x")
        result["trace_refs"] = [
            f"trace:{trace_id_hex}",
            f"span:{span_id_hex}",
        ]


def export_evaluation(
    result: dict[str, Any],
    span: trace.Span | None = None,
) -> dict[str, Any]:
    """Export evaluation result to OTel.

    If no span is provided, uses the current active span.
    Sets span attributes and records an evaluation event.

    Args:
        result: Evaluation output contract dict.
        span: Optional OTel span. Uses current active span if None.

    Returns:
        The result dict, updated with trace_refs if span context is valid.
    """
    if span is None:
        span = trace.get_current_span()

    # Only export if we have a recording span
    if not span.is_recording():
        return result

    set_span_attributes(span, result)
    record_evaluation_event(span, result)

    return result
