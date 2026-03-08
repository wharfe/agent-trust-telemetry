"""Tests for risk scoring and action recommendation engine."""


from att.evaluator import Finding
from att.scorer import score


def _finding(
    policy_class=None,
    anomaly_indicator=None,
    confidence=0.85,
    severity="high",
    weight=1.0,
    matched_field="content",
    rule_id="test-rule",
):
    return Finding(
        rule_id=rule_id,
        rule_description="test finding",
        policy_class=policy_class,
        anomaly_indicator=anomaly_indicator,
        confidence=confidence,
        severity=severity,
        weight=weight,
        matched_field=matched_field,
        matched_text="test match",
    )


class TestRiskScoreComputation:
    def test_no_findings_returns_zero(self):
        result = score([])
        assert result.risk_score == 0

    def test_single_finding_score(self):
        result = score([_finding(policy_class="instruction_override", confidence=0.85)])
        # base = 0.85 * 1.0 = 0.85, bonus = min(0.2, 0.05 * 0) = 0
        # score = min(100, round(0.85 * 100)) = 85
        assert result.risk_score == 85

    def test_multiple_findings_bonus(self):
        findings = [
            _finding(policy_class="instruction_override", confidence=0.85),
            _finding(anomaly_indicator="hidden_instruction_embedding", confidence=0.70),
        ]
        result = score(findings)
        # base = 0.85, bonus = min(0.2, 0.05 * 1) = 0.05
        # score = min(100, round(0.90 * 100)) = 90
        assert result.risk_score == 90

    def test_bonus_capped_at_20(self):
        findings = [
            _finding(
                policy_class="instruction_override",
                confidence=0.80,
                rule_id="r1",
            ),
            _finding(
                policy_class="privilege_escalation_attempt",
                confidence=0.70,
                rule_id="r2",
            ),
            _finding(
                policy_class="secret_access_attempt",
                confidence=0.60,
                rule_id="r3",
            ),
            _finding(
                policy_class="exfiltration_attempt",
                confidence=0.50,
                rule_id="r4",
            ),
            _finding(
                policy_class="tool_misuse_attempt",
                confidence=0.40,
                rule_id="r5",
            ),
        ]
        result = score(findings)
        # base = 0.80, bonus = min(0.2, 0.05 * 4) = 0.20
        # score = min(100, round(1.00 * 100)) = 100
        assert result.risk_score == 100

    def test_deduplication_same_class(self):
        findings = [
            _finding(
                policy_class="instruction_override",
                confidence=0.85,
                rule_id="r1",
            ),
            _finding(
                policy_class="instruction_override",
                confidence=0.70,
                rule_id="r2",
            ),
        ]
        result = score(findings)
        # Deduped to 1 finding (highest confidence), no bonus
        # base = 0.85, bonus = 0
        assert result.risk_score == 85


class TestSeverity:
    def test_no_findings_low(self):
        result = score([])
        assert result.severity == "low"

    def test_single_high(self):
        result = score([_finding(policy_class="instruction_override", severity="high")])
        assert result.severity == "high"

    def test_max_severity_wins(self):
        findings = [
            _finding(policy_class="instruction_override", severity="medium"),
            _finding(
                anomaly_indicator="hidden_instruction_embedding", severity="critical"
            ),
        ]
        result = score(findings)
        assert result.severity == "critical"


class TestRecommendedAction:
    def test_no_findings_observe(self):
        result = score([])
        assert result.recommended_action == "observe"

    def test_below_confidence_threshold_observe(self):
        result = score([
            _finding(policy_class="instruction_override", confidence=0.4, severity="high")
        ])
        assert result.recommended_action == "observe"

    def test_p0_critical_block(self):
        result = score([
            _finding(
                policy_class="instruction_override",
                confidence=0.9,
                severity="critical",
            )
        ])
        assert result.recommended_action == "block"

    def test_p0_high_quarantine(self):
        result = score([
            _finding(
                policy_class="instruction_override",
                confidence=0.85,
                severity="high",
            )
        ])
        assert result.recommended_action == "quarantine"

    def test_p0_medium_warn(self):
        result = score([
            _finding(
                policy_class="instruction_override",
                confidence=0.85,
                severity="medium",
            )
        ])
        assert result.recommended_action == "warn"

    def test_p1_medium_warn(self):
        result = score([
            _finding(
                policy_class="exfiltration_attempt",
                confidence=0.85,
                severity="medium",
            )
        ])
        assert result.recommended_action == "warn"

    def test_parent_flagged_propagation_quarantine(self):
        """parent_flagged_propagation with confidence >= 0.5 → quarantine."""
        finding = _finding(
            anomaly_indicator="provenance_or_metadata_drift",
            confidence=0.7,
            severity="high",
            matched_field="__parent_flagged_propagation__",
            rule_id="__inheritance__",
        )
        result = score([finding])
        assert result.recommended_action == "quarantine"


class TestOutputStructure:
    def test_policy_classes_in_output(self):
        result = score([
            _finding(policy_class="instruction_override", confidence=0.85, severity="high")
        ])
        assert len(result.policy_classes) == 1
        assert result.policy_classes[0]["name"] == "instruction_override"
        assert result.policy_classes[0]["confidence"] == 0.85

    def test_anomaly_indicators_in_output(self):
        finding = _finding(
            anomaly_indicator="provenance_or_metadata_drift",
            confidence=0.7,
            severity="high",
            matched_field="__parent_flagged_propagation__",
            rule_id="__inheritance__",
        )
        result = score([finding])
        assert len(result.anomaly_indicators) == 1
        assert result.anomaly_indicators[0]["name"] == "provenance_or_metadata_drift"
        assert result.anomaly_indicators[0]["subclass"] == "parent_flagged_propagation"

    def test_evidence_generated(self):
        result = score([
            _finding(policy_class="instruction_override", confidence=0.85, severity="high")
        ])
        assert len(result.evidence) > 0
