"""TrustState — LangGraph state extension for trust telemetry results."""

from __future__ import annotations

from typing import Any, TypedDict


class TrustState(TypedDict, total=False):
    """Mix-in for LangGraph state that carries trust evaluation results.

    Usage::

        class MyState(AgentState, TrustState):
            pass
    """

    trust_last_result: dict[str, Any] | None
    trust_session_flags: list[dict[str, Any]]
    trust_quarantined: bool
