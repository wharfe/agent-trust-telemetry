#!/usr/bin/env python3
"""Demo scenario: tool description poisoning → one-hop inheritance → quarantine.

This script demonstrates the core value proposition of agent-trust-telemetry:

1. A malicious MCP server embeds hidden instructions in a tool description
2. Agent A calls the poisoned tool — hidden_instruction_embedding detected (warn)
3. Agent A forwards results to Agent B — parent_flagged_propagation triggers (quarantine)
4. Agent B forwards to Agent C — one-hop limit prevents further propagation cascade

Run standalone:
    python demo/run_demo.py

Run with OTel export (requires docker-compose up):
    python demo/run_demo.py --otel
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src to path for standalone execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from att.pipeline import EvaluationPipeline  # noqa: E402

SCENARIO_FILE = Path(__file__).parent / "scenario.jsonl"

# ANSI colors for terminal output
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

ACTION_COLORS = {
    "observe": GREEN,
    "warn": YELLOW,
    "quarantine": RED,
    "block": RED + BOLD,
}


def _print_header() -> None:
    print()
    print(f"{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}  agent-trust-telemetry Demo{RESET}")
    print(f"{BOLD}  Scenario: Tool Description Poisoning → One-hop Inheritance{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")
    print()


def _print_step(step: int, envelope: dict, result: dict) -> None:
    action = result["recommended_action"]
    color = ACTION_COLORS.get(action, RESET)
    score = result["risk_score"]
    severity = result["severity"]

    print(f"{BOLD}--- Step {step} ---{RESET}")
    print(f"  Message:  {envelope['message_id']}")
    print(f"  Flow:     {envelope['sender']} → {envelope['receiver']}")
    print(f"  Channel:  {envelope['channel']}")
    print(f"  Phase:    {envelope['execution_phase']}")

    if envelope.get("tool_context", {}) and envelope["tool_context"].get("tool_name"):
        print(f"  Tool:     {envelope['tool_context']['tool_name']}")

    print()
    print(f"  {color}Action:     {action.upper()}{RESET}")
    print(f"  Risk Score: {score}")
    print(f"  Severity:   {severity}")

    if result["policy_classes"]:
        classes = ", ".join(
            f"{pc['name']} ({pc['confidence']:.2f})"
            for pc in result["policy_classes"]
        )
        print(f"  Policy:     {classes}")

    if result["anomaly_indicators"]:
        indicators = ", ".join(
            f"{ai['name']}"
            + (f"/{ai['subclass']}" if ai.get("subclass") else "")
            + f" ({ai['confidence']:.2f})"
            for ai in result["anomaly_indicators"]
        )
        print(f"  Anomaly:    {indicators}")

    if result["evidence"]:
        print("  Evidence:")
        for ev in result["evidence"]:
            print(f"    - {ev}")

    if result.get("trace_refs"):
        print(f"  Trace Refs: {', '.join(result['trace_refs'])}")

    print()


def _print_summary(results: list[dict]) -> None:
    print(f"{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}  Summary{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")
    print()

    quarantined = [r for r in results if r["recommended_action"] == "quarantine"]
    warned = [r for r in results if r["recommended_action"] == "warn"]
    blocked = [r for r in results if r["recommended_action"] == "block"]
    clean = [r for r in results if r["recommended_action"] == "observe"]

    print(f"  Total messages:  {len(results)}")
    print(f"  {GREEN}Observe:{RESET}          {len(clean)}")
    print(f"  {YELLOW}Warn:{RESET}             {len(warned)}")
    print(f"  {RED}Quarantine:{RESET}       {len(quarantined)}")
    print(f"  {RED}{BOLD}Block:{RESET}            {len(blocked)}")
    print()

    if quarantined:
        print(f"  {RED}Quarantined messages:{RESET}")
        for r in quarantined:
            print(f"    - {r['message_id']} (score: {r['risk_score']})")
        print()

    print(f"  {CYAN}This demonstrates how agent-trust-telemetry detects")
    print("  tool description poisoning and tracks contamination")
    print(f"  propagation through the agent communication graph.{RESET}")
    print()


def run_demo(otel_enabled: bool = False) -> list[dict]:
    """Run the demo scenario and return results."""
    pipeline = EvaluationPipeline(otel_enabled=otel_enabled)

    with open(SCENARIO_FILE) as f:
        envelopes = [json.loads(line) for line in f if line.strip()]

    results: list[dict] = []
    _print_header()

    if otel_enabled:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter()
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            tracer = trace.get_tracer("att-demo")
            print(f"  {CYAN}OTel export enabled → OTLP gRPC endpoint{RESET}")
            print()
        except ImportError:
            print(f"  {YELLOW}OTLP exporter not installed. Run:")
            print(f"    pip install opentelemetry-exporter-otlp-proto-grpc{RESET}")
            print()
            otel_enabled = False

    for i, envelope in enumerate(envelopes, 1):
        if otel_enabled:
            with tracer.start_as_current_span(  # type: ignore[possibly-undefined]
                f"evaluate-msg-{i}",
                attributes={
                    "message.sender": envelope["sender"],
                    "message.receiver": envelope["receiver"],
                    "message.channel": envelope["channel"],
                },
            ):
                result = pipeline.evaluate(envelope)
        else:
            result = pipeline.evaluate(envelope)

        results.append(result)
        _print_step(i, envelope, result)

    _print_summary(results)

    # Write results to JSONL
    output_file = Path(__file__).parent / "results.jsonl"
    with open(output_file, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Results written to {output_file}")
    print()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent-trust-telemetry demo")
    parser.add_argument(
        "--otel",
        action="store_true",
        help="Enable OTel export (requires OTLP endpoint)",
    )
    args = parser.parse_args()
    run_demo(otel_enabled=args.otel)


if __name__ == "__main__":
    main()
