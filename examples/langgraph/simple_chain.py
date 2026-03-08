#!/usr/bin/env python3
"""Minimal 2-node LangGraph chain with trust telemetry.

Demonstrates that adding trust telemetry to a LangGraph graph requires
only one extra line: passing a ``TrustTelemetryCallback`` to each node.

Usage::

    pip install agent-trust-telemetry[langgraph]
    python examples/langgraph/simple_chain.py
"""

from __future__ import annotations

from typing import Any

from att.integrations.langgraph.callback import TrustTelemetryCallback
from att.pipeline import EvaluationPipeline


def agent_a_fn(state: dict[str, Any]) -> dict[str, Any]:
    """First agent — produces a message."""
    print(f"  [agent_a] Processing: {state.get('input', '')}")
    state.setdefault("messages", [])
    state["messages"].append({"content": f"Agent A processed: {state.get('input', '')}"})
    return state


def agent_b_fn(state: dict[str, Any]) -> dict[str, Any]:
    """Second agent — consumes agent_a's output."""
    last_msg = ""
    msgs = state.get("messages", [])
    if msgs:
        last_msg = msgs[-1].get("content", "")
    print(f"  [agent_b] Received: {last_msg}")
    state["messages"].append({"content": f"Agent B processed: {last_msg}"})
    return state


def run_with_callback() -> None:
    """Run the 2-node chain with trust telemetry callbacks."""
    pipeline = EvaluationPipeline()
    callback = TrustTelemetryCallback(pipeline=pipeline)

    state: dict[str, Any] = {
        "input": "Hello, world!",
        "session_id": "simple-chain-demo",
        "trace_id": "trace:simple-demo",
        "messages": [{"content": "Hello, world!"}],
    }

    print("=== Simple Chain Demo ===\n")

    # Node A
    print("Step 1: agent_a")
    callback.on_node_start("agent_a", state, state)
    result_a = state["trust_last_result"]
    print(f"  Trust: action={result_a['recommended_action']}, score={result_a['risk_score']}")
    state = agent_a_fn(state)
    print()

    # Node B
    print("Step 2: agent_b")
    callback.on_node_start("agent_b", state, state)
    result_b = state["trust_last_result"]
    print(f"  Trust: action={result_b['recommended_action']}, score={result_b['risk_score']}")
    state = agent_b_fn(state)
    print()

    print("=== Results ===")
    print(f"  Total evaluations: {len(state.get('trust_session_flags', []))}")
    print(f"  Quarantined: {state.get('trust_quarantined', False)}")
    print("  All messages passed trust evaluation.")


if __name__ == "__main__":
    run_with_callback()
