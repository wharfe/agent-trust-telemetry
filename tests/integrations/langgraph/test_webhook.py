"""Tests for QuarantineWebhookNotifier."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from att.integrations.langgraph.webhook import QuarantineWebhookNotifier


def _quarantine_evaluation():
    return {
        "message_id": "msg:test-001",
        "risk_score": 80,
        "severity": "high",
        "recommended_action": "quarantine",
        "evidence": ["Test evidence"],
    }


def _warn_evaluation():
    return {
        "message_id": "msg:test-002",
        "risk_score": 40,
        "severity": "medium",
        "recommended_action": "warn",
        "evidence": ["Minor issue"],
    }


def _block_evaluation():
    return {
        "message_id": "msg:test-003",
        "risk_score": 95,
        "severity": "critical",
        "recommended_action": "block",
        "evidence": ["Critical threat"],
    }


class TestWebhookNotifiedOnQuarantine:
    @patch("att.integrations.langgraph.webhook.urllib.request.urlopen")
    def test_post_sent_on_quarantine(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(url="https://example.com/hook")
        ev = _quarantine_evaluation()
        notifier.notify(ev, "agent_a")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        body = json.loads(req.data)
        assert body["node_name"] == "agent_a"
        assert body["evaluation"]["recommended_action"] == "quarantine"


class TestWebhookNotNotifiedOnWarn:
    @patch("att.integrations.langgraph.webhook.urllib.request.urlopen")
    def test_no_post_on_warn_default_config(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(url="https://example.com/hook")
        notifier.notify(_warn_evaluation(), "agent_a")
        mock_urlopen.assert_not_called()


class TestWebhookErrorIgnoredByDefault:
    @patch(
        "att.integrations.langgraph.webhook.urllib.request.urlopen",
        side_effect=Exception("connection refused"),
    )
    def test_error_swallowed(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(url="https://example.com/hook")
        # Should not raise
        notifier.notify(_quarantine_evaluation(), "agent_a")

    @patch(
        "att.integrations.langgraph.webhook.urllib.request.urlopen",
        side_effect=Exception("connection refused"),
    )
    def test_error_raised_when_configured(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(
            url="https://example.com/hook",
            on_error="raise",
        )
        with pytest.raises(Exception, match="connection refused"):
            notifier.notify(_quarantine_evaluation(), "agent_a")


class TestWebhookRespectsActionFilter:
    @patch("att.integrations.langgraph.webhook.urllib.request.urlopen")
    def test_custom_actions_filter(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(
            url="https://example.com/hook",
            actions=["block"],
        )
        # quarantine should NOT trigger
        notifier.notify(_quarantine_evaluation(), "agent_a")
        mock_urlopen.assert_not_called()

        # block SHOULD trigger
        notifier.notify(_block_evaluation(), "agent_b")
        mock_urlopen.assert_called_once()

    @patch("att.integrations.langgraph.webhook.urllib.request.urlopen")
    def test_warn_included_when_configured(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(
            url="https://example.com/hook",
            actions=["warn", "quarantine", "block"],
        )
        notifier.notify(_warn_evaluation(), "agent_a")
        mock_urlopen.assert_called_once()


class TestWebhookHeaders:
    @patch("att.integrations.langgraph.webhook.urllib.request.urlopen")
    def test_custom_headers_included(self, mock_urlopen):
        notifier = QuarantineWebhookNotifier(
            url="https://example.com/hook",
            headers={"Authorization": "Bearer test-token"},
        )
        notifier.notify(_quarantine_evaluation(), "agent_a")
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer test-token"
        assert req.get_header("Content-type") == "application/json"
