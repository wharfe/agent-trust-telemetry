"""QuarantineWebhookNotifier — POST evaluation results on quarantine/block."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class QuarantineWebhookNotifier:
    """Send webhook notifications when quarantine or block actions occur.

    Args:
        url: Destination URL for POST requests.
        actions: Actions that trigger notification (default: quarantine, block).
        headers: Extra HTTP headers (e.g. authorization tokens).
        timeout: Request timeout in seconds.
        on_error: ``"ignore"`` swallows failures, ``"raise"`` re-raises.
    """

    def __init__(
        self,
        url: str,
        actions: list[str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
        on_error: str = "ignore",
    ) -> None:
        self.url = url
        self.actions = actions or ["quarantine", "block"]
        self.headers = headers or {}
        self.timeout = timeout
        if on_error not in ("ignore", "raise"):
            msg = f"on_error must be 'ignore' or 'raise', got '{on_error}'"
            raise ValueError(msg)
        self.on_error = on_error

    def notify(self, evaluation: dict[str, Any], node_name: str) -> None:
        """Send evaluation result if the action matches the configured filter."""
        action = evaluation.get("recommended_action", "observe")
        if action not in self.actions:
            return

        payload = {
            "node_name": node_name,
            "evaluation": evaluation,
        }
        body = json.dumps(payload).encode("utf-8")

        req_headers = {
            "Content-Type": "application/json",
            **self.headers,
        }
        req = urllib.request.Request(
            self.url,
            data=body,
            headers=req_headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except Exception:
            if self.on_error == "raise":
                raise
            logger.warning("Webhook notification failed for node '%s'", node_name, exc_info=True)
