"""Tests for tool metadata drift tracking."""

from att.metadata import MetadataTracker


class TestMetadataTracker:
    def test_first_observation_no_finding(self):
        tracker = MetadataTracker()
        result = tracker.check("sess-1", "agent_a", "web_search", "sha256:" + "a" * 64)
        assert result is None

    def test_same_hash_no_finding(self):
        tracker = MetadataTracker()
        h = "sha256:" + "a" * 64
        tracker.check("sess-1", "agent_a", "web_search", h)
        result = tracker.check("sess-1", "agent_a", "web_search", h)
        assert result is None

    def test_different_hash_triggers_drift(self):
        tracker = MetadataTracker()
        h1 = "sha256:" + "a" * 64
        h2 = "sha256:" + "b" * 64
        tracker.check("sess-1", "agent_a", "web_search", h1)
        result = tracker.check("sess-1", "agent_a", "web_search", h2)
        assert result is not None
        assert result.anomaly_indicator == "provenance_or_metadata_drift"
        assert result.matched_field == "__tool_metadata_drift__"
        assert result.confidence == 0.85

    def test_different_sender_same_tool_no_drift(self):
        tracker = MetadataTracker()
        h1 = "sha256:" + "a" * 64
        h2 = "sha256:" + "b" * 64
        tracker.check("sess-1", "agent_a", "web_search", h1)
        result = tracker.check("sess-1", "agent_b", "web_search", h2)
        assert result is None  # Different sender, so it's a first observation

    def test_different_session_no_drift(self):
        tracker = MetadataTracker()
        h1 = "sha256:" + "a" * 64
        h2 = "sha256:" + "b" * 64
        tracker.check("sess-1", "agent_a", "web_search", h1)
        result = tracker.check("sess-2", "agent_a", "web_search", h2)
        assert result is None  # Different session

    def test_null_tool_name_no_tracking(self):
        tracker = MetadataTracker()
        result = tracker.check("sess-1", "agent_a", None, "sha256:" + "a" * 64)
        assert result is None

    def test_null_hash_no_tracking(self):
        tracker = MetadataTracker()
        result = tracker.check("sess-1", "agent_a", "web_search", None)
        assert result is None

    def test_clear(self):
        tracker = MetadataTracker()
        h1 = "sha256:" + "a" * 64
        h2 = "sha256:" + "b" * 64
        tracker.check("sess-1", "agent_a", "web_search", h1)
        tracker.clear()
        # After clear, next check is a first observation
        result = tracker.check("sess-1", "agent_a", "web_search", h2)
        assert result is None
