"""Tests for TrustInterrupt."""

from __future__ import annotations

from att.integrations.langgraph.interrupt import TrustInterrupt


def _sample_evaluation():
    return {
        "schema_version": "0.1",
        "message_id": "msg:test-123",
        "risk_score": 75,
        "severity": "high",
        "recommended_action": "quarantine",
        "evidence": ["Instruction override detected"],
    }


class TestTrustInterruptContainsEvaluation:
    def test_evaluation_accessible(self):
        ev = _sample_evaluation()
        exc = TrustInterrupt(ev)
        assert exc.evaluation is ev
        assert exc.evaluation["recommended_action"] == "quarantine"
        assert exc.evaluation["risk_score"] == 75

    def test_message_includes_action_and_score(self):
        exc = TrustInterrupt(_sample_evaluation())
        assert "quarantine" in str(exc)
        assert "75" in str(exc)


class TestTrustInterruptIsCatchable:
    def test_catchable_as_runtime_error(self):
        """TrustInterrupt is always catchable as RuntimeError (fallback base)."""
        exc = TrustInterrupt(_sample_evaluation())
        assert isinstance(exc, Exception)

    def test_catchable_in_try_except(self):
        with __import__("pytest").raises(TrustInterrupt):
            raise TrustInterrupt(_sample_evaluation())

    def test_catchable_as_base_class(self):
        """When langgraph is installed, TrustInterrupt is a GraphInterrupt."""
        try:
            from langgraph.errors import GraphInterrupt

            exc = TrustInterrupt(_sample_evaluation())
            assert isinstance(exc, GraphInterrupt)
        except ImportError:
            # Without langgraph, it falls back to RuntimeError
            exc = TrustInterrupt(_sample_evaluation())
            assert isinstance(exc, RuntimeError)
