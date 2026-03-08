"""Tests for one-hop risk inheritance."""


from att.inheritance import InheritanceConfig, check_parent_propagation


class TestParentPropagation:
    def test_no_parent_returns_none(self):
        assert check_parent_propagation(None) is None

    def test_parent_observe_no_propagation(self):
        parent = {"recommended_action": "observe", "message_id": "msg:abc", "risk_score": 10}
        assert check_parent_propagation(parent) is None

    def test_parent_warn_triggers_propagation(self):
        parent = {"recommended_action": "warn", "message_id": "msg:abc", "risk_score": 55}
        finding = check_parent_propagation(parent)
        assert finding is not None
        assert finding.confidence == 0.7
        assert finding.anomaly_indicator == "provenance_or_metadata_drift"
        assert finding.matched_field == "__parent_flagged_propagation__"

    def test_parent_quarantine_triggers_propagation(self):
        parent = {"recommended_action": "quarantine", "message_id": "msg:abc", "risk_score": 82}
        finding = check_parent_propagation(parent)
        assert finding is not None
        assert finding.confidence == 0.7

    def test_parent_block_triggers_propagation(self):
        parent = {"recommended_action": "block", "message_id": "msg:abc", "risk_score": 95}
        finding = check_parent_propagation(parent)
        assert finding is not None

    def test_propagated_confidence_from_config(self):
        config = InheritanceConfig(propagated_confidence=0.5)
        parent = {"recommended_action": "warn", "message_id": "msg:abc", "risk_score": 55}
        finding = check_parent_propagation(parent, config)
        assert finding is not None
        assert finding.confidence == 0.5

    def test_disabled_config(self):
        config = InheritanceConfig(enabled=False)
        parent = {"recommended_action": "block", "message_id": "msg:abc", "risk_score": 95}
        assert check_parent_propagation(parent, config) is None

    def test_evidence_includes_parent_info(self):
        parent = {"recommended_action": "warn", "message_id": "msg:parent123", "risk_score": 65}
        finding = check_parent_propagation(parent)
        assert finding is not None
        assert "msg:parent123" in finding.rule_description
        assert "65" in finding.rule_description
        assert "warn" in finding.rule_description
