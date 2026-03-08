"""Validation tests for Message Envelope and Output Contract JSON Schemas.

Tests cover both positive (valid) and negative (invalid) cases for each schema.
"""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "src" / "schemas"


@pytest.fixture
def envelope_schema() -> dict:
    """Load the Message Envelope JSON Schema."""
    with open(SCHEMA_DIR / "envelope.json") as f:
        return json.load(f)


@pytest.fixture
def output_schema() -> dict:
    """Load the Output Contract JSON Schema."""
    with open(SCHEMA_DIR / "output.json") as f:
        return json.load(f)


# --- Helper data ---

VALID_MSG_ID = "msg:550e8400-e29b-41d4-a716-446655440000"
VALID_PARENT_ID = "msg:660e8400-e29b-41d4-a716-446655440001"
VALID_TIMESTAMP = "2025-01-15T10:30:00Z"
VALID_CONTENT_HASH = "sha256:" + "a" * 64
VALID_DESC_HASH = "sha256:" + "b" * 64


def _minimal_envelope(**overrides) -> dict:
    """Build a minimal valid envelope message."""
    base = {
        "message_id": VALID_MSG_ID,
        "parent_message_id": None,
        "timestamp": VALID_TIMESTAMP,
        "sender": "agent_a",
        "receiver": "agent_b",
        "channel": "mcp",
        "role": "content",
        "execution_phase": "synthesis",
        "session_id": "sess-001",
        "trace_id": "trace-001",
        "turn_index": 0,
        "provenance": ["human", "agent_a"],
        "content": "Hello, world.",
        "content_hash": VALID_CONTENT_HASH,
    }
    base.update(overrides)
    return base


def _minimal_output(**overrides) -> dict:
    """Build a minimal valid output contract."""
    base = {
        "schema_version": "0.1",
        "message_id": VALID_MSG_ID,
        "trace_id": "trace-001",
        "session_id": "sess-001",
        "evaluated_at": VALID_TIMESTAMP,
        "risk_score": 0,
        "severity": "low",
        "policy_classes": [],
        "anomaly_indicators": [],
        "evidence": [],
        "recommended_action": "observe",
    }
    base.update(overrides)
    return base


# ===== Envelope Schema: Positive Cases =====


class TestEnvelopeValid:
    """Positive validation cases for Message Envelope schema."""

    def test_minimal_valid(self, envelope_schema):
        """Minimal valid envelope with all required fields."""
        jsonschema.validate(_minimal_envelope(), envelope_schema)

    def test_with_parent_message_id(self, envelope_schema):
        """Envelope with a parent_message_id set."""
        msg = _minimal_envelope(parent_message_id=VALID_PARENT_ID)
        jsonschema.validate(msg, envelope_schema)

    def test_with_tool_context(self, envelope_schema):
        """Envelope with full tool_context."""
        msg = _minimal_envelope(
            role="tool_call",
            execution_phase="tool_execution",
            tool_context={
                "tool_name": "web_search",
                "description_raw": "Search the web for information",
                "description_hash": VALID_DESC_HASH,
            },
        )
        jsonschema.validate(msg, envelope_schema)

    def test_tool_context_nullable_fields(self, envelope_schema):
        """Tool context with all nullable fields set to null."""
        msg = _minimal_envelope(
            tool_context={
                "tool_name": None,
                "description_raw": None,
                "description_hash": None,
            },
        )
        jsonschema.validate(msg, envelope_schema)

    def test_content_null(self, envelope_schema):
        """Content field can be null."""
        msg = _minimal_envelope(content=None)
        jsonschema.validate(msg, envelope_schema)

    def test_all_channels(self, envelope_schema):
        """All valid channel values are accepted."""
        for channel in ["mcp", "a2a", "internal", "unknown"]:
            msg = _minimal_envelope(channel=channel)
            jsonschema.validate(msg, envelope_schema)

    def test_all_roles(self, envelope_schema):
        """All valid role values are accepted."""
        for role in ["tool_call", "content", "system", "unknown"]:
            msg = _minimal_envelope(role=role)
            jsonschema.validate(msg, envelope_schema)

    def test_custom_execution_phase(self, envelope_schema):
        """Custom (non-core) execution_phase values are accepted."""
        msg = _minimal_envelope(execution_phase="langraph_node_pre_hook")
        jsonschema.validate(msg, envelope_schema)

    def test_high_turn_index(self, envelope_schema):
        """Large turn_index values are accepted."""
        msg = _minimal_envelope(turn_index=9999)
        jsonschema.validate(msg, envelope_schema)


# ===== Envelope Schema: Negative Cases =====


class TestEnvelopeInvalid:
    """Negative validation cases for Message Envelope schema."""

    def test_missing_message_id(self, envelope_schema):
        """message_id is required."""
        msg = _minimal_envelope()
        del msg["message_id"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_invalid_message_id_format(self, envelope_schema):
        """message_id must match msg:uuid-v4 pattern."""
        msg = _minimal_envelope(message_id="not-a-valid-id")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_invalid_message_id_no_prefix(self, envelope_schema):
        """message_id must have msg: prefix."""
        msg = _minimal_envelope(
            message_id="550e8400-e29b-41d4-a716-446655440000"
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_invalid_channel(self, envelope_schema):
        """Invalid channel value is rejected."""
        msg = _minimal_envelope(channel="http")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_invalid_role(self, envelope_schema):
        """Invalid role value is rejected."""
        msg = _minimal_envelope(role="assistant")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_empty_sender(self, envelope_schema):
        """Empty sender string is rejected."""
        msg = _minimal_envelope(sender="")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_empty_provenance(self, envelope_schema):
        """Empty provenance array is rejected."""
        msg = _minimal_envelope(provenance=[])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_negative_turn_index(self, envelope_schema):
        """Negative turn_index is rejected."""
        msg = _minimal_envelope(turn_index=-1)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_invalid_content_hash_format(self, envelope_schema):
        """content_hash must match sha256:hex pattern."""
        msg = _minimal_envelope(content_hash="md5:abc123")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_invalid_description_hash_format(self, envelope_schema):
        """description_hash must match sha256:hex pattern."""
        msg = _minimal_envelope(
            tool_context={
                "tool_name": "test",
                "description_raw": "test",
                "description_hash": "sha256:tooshort",
            },
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_additional_properties_rejected(self, envelope_schema):
        """Unknown top-level properties are rejected."""
        msg = _minimal_envelope(unknown_field="value")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_tool_context_additional_properties_rejected(self, envelope_schema):
        """Unknown tool_context properties are rejected."""
        msg = _minimal_envelope(
            tool_context={
                "tool_name": "test",
                "extra_field": "value",
            },
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)

    def test_turn_index_float_rejected(self, envelope_schema):
        """turn_index must be an integer, not float."""
        msg = _minimal_envelope(turn_index=1.5)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(msg, envelope_schema)


# ===== Output Contract: Positive Cases =====


class TestOutputValid:
    """Positive validation cases for Output Contract schema."""

    def test_minimal_observe(self, output_schema):
        """Minimal valid output with observe action."""
        jsonschema.validate(_minimal_output(), output_schema)

    def test_with_policy_classes(self, output_schema):
        """Output with policy class findings."""
        out = _minimal_output(
            risk_score=85,
            severity="high",
            policy_classes=[
                {
                    "name": "instruction_override",
                    "confidence": 0.91,
                    "severity": "high",
                }
            ],
            recommended_action="quarantine",
        )
        jsonschema.validate(out, output_schema)

    def test_with_anomaly_indicators(self, output_schema):
        """Output with anomaly indicator findings."""
        out = _minimal_output(
            risk_score=70,
            severity="high",
            anomaly_indicators=[
                {
                    "name": "provenance_or_metadata_drift",
                    "subclass": "parent_flagged_propagation",
                    "confidence": 0.70,
                    "severity": "high",
                }
            ],
            recommended_action="quarantine",
        )
        jsonschema.validate(out, output_schema)

    def test_anomaly_indicator_without_subclass(self, output_schema):
        """Anomaly indicator with null subclass."""
        out = _minimal_output(
            anomaly_indicators=[
                {
                    "name": "hidden_instruction_embedding",
                    "subclass": None,
                    "confidence": 0.80,
                    "severity": "high",
                }
            ],
        )
        jsonschema.validate(out, output_schema)

    def test_with_trace_refs(self, output_schema):
        """Output with optional trace_refs."""
        out = _minimal_output(
            trace_refs=["span:abc123", "event:def456"],
        )
        jsonschema.validate(out, output_schema)

    def test_with_evidence(self, output_schema):
        """Output with evidence strings."""
        out = _minimal_output(
            evidence=[
                "override phrase detected near end of long context",
                "parent message msg:xxx was flagged",
            ],
        )
        jsonschema.validate(out, output_schema)

    def test_all_actions(self, output_schema):
        """All valid recommended_action values are accepted."""
        for action in ["observe", "warn", "quarantine", "block"]:
            out = _minimal_output(recommended_action=action)
            jsonschema.validate(out, output_schema)

    def test_all_severity_levels(self, output_schema):
        """All valid severity values are accepted."""
        for sev in ["low", "medium", "high", "critical"]:
            out = _minimal_output(severity=sev)
            jsonschema.validate(out, output_schema)

    def test_risk_score_boundaries(self, output_schema):
        """Risk score at boundaries (0 and 100) are valid."""
        jsonschema.validate(_minimal_output(risk_score=0), output_schema)
        jsonschema.validate(_minimal_output(risk_score=100), output_schema)

    def test_all_policy_class_names(self, output_schema):
        """All defined policy class names are accepted."""
        names = [
            "instruction_override",
            "privilege_escalation_attempt",
            "secret_access_attempt",
            "exfiltration_attempt",
            "tool_misuse_attempt",
        ]
        for name in names:
            out = _minimal_output(
                policy_classes=[{"name": name, "confidence": 0.5, "severity": "medium"}]
            )
            jsonschema.validate(out, output_schema)


# ===== Output Contract: Negative Cases =====


class TestOutputInvalid:
    """Negative validation cases for Output Contract schema."""

    def test_missing_schema_version(self, output_schema):
        """schema_version is required."""
        out = _minimal_output()
        del out["schema_version"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_wrong_schema_version(self, output_schema):
        """schema_version must be exactly '0.1'."""
        out = _minimal_output(schema_version="1.0")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_risk_score_over_100(self, output_schema):
        """risk_score above 100 is rejected."""
        out = _minimal_output(risk_score=101)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_risk_score_negative(self, output_schema):
        """Negative risk_score is rejected."""
        out = _minimal_output(risk_score=-1)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_invalid_severity(self, output_schema):
        """Invalid severity value is rejected."""
        out = _minimal_output(severity="extreme")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_invalid_action(self, output_schema):
        """Invalid recommended_action is rejected."""
        out = _minimal_output(recommended_action="ignore")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_invalid_policy_class_name(self, output_schema):
        """Unknown policy class name is rejected."""
        out = _minimal_output(
            policy_classes=[
                {"name": "unknown_class", "confidence": 0.5, "severity": "low"}
            ]
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_invalid_anomaly_indicator_name(self, output_schema):
        """Unknown anomaly indicator name is rejected."""
        out = _minimal_output(
            anomaly_indicators=[
                {"name": "unknown_indicator", "confidence": 0.5, "severity": "low"}
            ]
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_confidence_above_1(self, output_schema):
        """Confidence above 1.0 is rejected."""
        out = _minimal_output(
            policy_classes=[
                {"name": "instruction_override", "confidence": 1.5, "severity": "high"}
            ]
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_confidence_negative(self, output_schema):
        """Negative confidence is rejected."""
        out = _minimal_output(
            policy_classes=[
                {"name": "instruction_override", "confidence": -0.1, "severity": "high"}
            ]
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_additional_properties_rejected(self, output_schema):
        """Unknown top-level properties are rejected."""
        out = _minimal_output(extra="value")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)

    def test_invalid_message_id_format(self, output_schema):
        """message_id must match msg:uuid-v4 pattern."""
        out = _minimal_output(message_id="bad-id")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(out, output_schema)
