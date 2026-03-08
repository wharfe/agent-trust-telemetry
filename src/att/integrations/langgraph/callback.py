"""TrustTelemetryCallback — LangGraph pre/post hook for trust evaluation."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from att.integrations.langgraph.interrupt import TrustInterrupt
from att.integrations.langgraph.webhook import QuarantineWebhookNotifier
from att.pipeline import EvaluationPipeline


def _sha256(text: str) -> str:
    """Return sha256:hex digest of text."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _coerce_content_to_str(raw: object) -> str | None:
    """Coerce content to a string, handling multipart lists."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        # Multipart content: [{"type": "text", "text": "..."}, ...]
        parts: list[str] = []
        for part in raw:
            if isinstance(part, dict):
                text = part.get("text")
                if text is not None:
                    parts.append(str(text))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts) if parts else str(raw)
    return str(raw)


def _extract_content(inputs: dict[str, Any]) -> str | None:
    """Extract message content from LangGraph node inputs."""
    messages = inputs.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            return _coerce_content_to_str(last.get("content"))
        # LangChain message objects
        if hasattr(last, "content"):
            return _coerce_content_to_str(last.content)
    # Fallback: look for a direct content key
    if "content" in inputs:
        return _coerce_content_to_str(inputs["content"])
    return None


def _extract_tool_context(inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract tool context from LangGraph node inputs if present."""
    tool_ctx = inputs.get("tool_context")
    if isinstance(tool_ctx, dict):
        return tool_ctx
    return {}


class TrustTelemetryCallback:
    """LangGraph callback that evaluates messages through the att pipeline.

    Args:
        pipeline: An ``EvaluationPipeline`` instance. If not provided, a
            default pipeline is created.
        on_quarantine: ``"interrupt"`` raises ``TrustInterrupt``;
            ``"flag_and_continue"`` sets ``state["trust_quarantined"]``.
        on_block: Same options as *on_quarantine*. Defaults to ``"interrupt"``.
        on_warn: Same options as *on_quarantine*. Defaults to
            ``"flag_and_continue"``.
        webhook_notifier: Optional notifier for quarantine/block events.
        evaluate_outputs: Whether to evaluate node outputs via
            ``on_node_end``. Defaults to ``False``.
    """

    def __init__(
        self,
        pipeline: EvaluationPipeline | None = None,
        on_quarantine: str = "interrupt",
        on_block: str = "interrupt",
        on_warn: str = "flag_and_continue",
        webhook_notifier: QuarantineWebhookNotifier | None = None,
        evaluate_outputs: bool = False,
    ) -> None:
        self.pipeline = pipeline or EvaluationPipeline()
        self.on_quarantine = on_quarantine
        self.on_block = on_block
        self.on_warn = on_warn
        self.webhook_notifier = webhook_notifier
        self.evaluate_outputs = evaluate_outputs
        # Track last sender per session for provenance chain
        self._last_sender: dict[str, str] = {}

    def on_node_start(
        self,
        node_name: str,
        inputs: dict[str, Any],
        state: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Evaluate input message before node execution.

        Builds a ``MessageEnvelope`` from LangGraph inputs, runs the
        evaluation pipeline, and writes results into *state*.
        """
        self._evaluate_and_act(node_name, inputs, state)

    def on_node_end(
        self,
        node_name: str,
        outputs: dict[str, Any],
        state: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Evaluate output message after node execution (optional).

        Only runs when ``evaluate_outputs=True``.
        """
        if not self.evaluate_outputs:
            return
        self._evaluate_and_act(node_name, outputs, state, is_output=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_and_act(
        self,
        node_name: str,
        data: dict[str, Any],
        state: dict[str, Any],
        *,
        is_output: bool = False,
    ) -> None:
        """Core evaluation + action logic shared by start/end hooks."""
        envelope = self._build_envelope(node_name, data, state, is_output=is_output)
        result = self.pipeline.evaluate(envelope)

        # Write result into state
        state["trust_last_result"] = result
        flags: list[dict[str, Any]] = state.get("trust_session_flags") or []
        flags.append(result)
        state["trust_session_flags"] = flags

        # Track sender for next node
        session_id = state.get("session_id", "default")
        self._last_sender[session_id] = node_name

        # Webhook notification
        if self.webhook_notifier is not None:
            self.webhook_notifier.notify(result, node_name)

        # Action handling
        action = result.get("recommended_action", "observe")
        self._handle_action(action, result, state)

    def _handle_action(
        self,
        action: str,
        result: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        """Apply the configured response for the given action level."""
        if action == "block":
            policy = self.on_block
        elif action == "quarantine":
            policy = self.on_quarantine
        elif action == "warn":
            policy = self.on_warn
        else:
            return

        if policy == "interrupt":
            state["trust_quarantined"] = True
            raise TrustInterrupt(result)

        # flag_and_continue
        if action in ("quarantine", "block"):
            state["trust_quarantined"] = True

    def _build_envelope(
        self,
        node_name: str,
        data: dict[str, Any],
        state: dict[str, Any],
        *,
        is_output: bool = False,
    ) -> dict[str, Any]:
        """Build a MessageEnvelope dict from LangGraph data."""
        session_id = state.get("session_id", "default")
        trace_id = state.get("trace_id", f"trace:{uuid.uuid4()}")

        # Determine sender/receiver
        last_sender = self._last_sender.get(session_id, "__start__")
        if is_output:
            sender = node_name
            receiver = "__next__"
        else:
            sender = last_sender
            receiver = node_name

        # Parent message ID from previous evaluation
        last_result = state.get("trust_last_result")
        parent_message_id = None
        if isinstance(last_result, dict):
            parent_message_id = last_result.get("message_id")

        content = _extract_content(data)
        content_text = content or ""
        tool_context = _extract_tool_context(data)

        message_id = f"msg:{uuid.uuid4()}"

        # Provenance chain
        provenance = [sender]
        if sender != last_sender and last_sender != "__start__":
            provenance.insert(0, last_sender)

        turn_index = len(state.get("trust_session_flags") or [])

        envelope: dict[str, Any] = {
            "message_id": message_id,
            "parent_message_id": parent_message_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": sender,
            "receiver": receiver,
            "channel": "internal",
            "role": "tool_call" if tool_context.get("tool_name") else "content",
            "execution_phase": node_name,
            "session_id": session_id,
            "trace_id": trace_id,
            "turn_index": turn_index,
            "provenance": provenance,
            "content": content,
            "content_hash": _sha256(content_text),
        }

        if tool_context:
            envelope["tool_context"] = tool_context

        return envelope
