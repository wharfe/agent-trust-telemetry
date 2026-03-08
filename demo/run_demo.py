#!/usr/bin/env python3
"""Run agent-trust-telemetry demo scenarios.

Available scenarios:
  tool_poisoning       — MCP tool description poisoning → one-hop inheritance (default)
  metadata_drift       — Tool description silently mutated mid-session
  data_exfiltration    — Secret extraction → external endpoint exfiltration chain
  privilege_escalation — Privilege escalation + destructive SQL injection via tool misuse

Usage:
    python demo/run_demo.py                          # default scenario
    python demo/run_demo.py --scenario metadata_drift
    python demo/run_demo.py --scenario all           # run all scenarios
    python demo/run_demo.py --otel                   # with OTel export
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add src to path for standalone execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from att.pipeline import EvaluationPipeline  # noqa: E402

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# Legacy location fallback
LEGACY_SCENARIO = Path(__file__).parent / "scenario.jsonl"

SCENARIO_TITLES: dict[str, str] = {
    "tool_poisoning": "Tool Description Poisoning → One-hop Inheritance",
    "metadata_drift": "Tool Metadata Drift — Silent Description Mutation",
    "data_exfiltration": "Secret Extraction → Data Exfiltration Chain",
    "privilege_escalation": "Privilege Escalation + Destructive SQL Injection",
}

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


def _list_scenarios() -> list[str]:
    """Return available scenario names."""
    scenarios = sorted(p.stem for p in SCENARIOS_DIR.glob("*.jsonl"))
    if not scenarios and LEGACY_SCENARIO.exists():
        scenarios = ["tool_poisoning"]
    return scenarios


def _load_scenario(name: str) -> list[dict[str, Any]]:
    """Load scenario messages from JSONL file."""
    path = SCENARIOS_DIR / f"{name}.jsonl"
    if not path.exists() and name == "tool_poisoning" and LEGACY_SCENARIO.exists():
        path = LEGACY_SCENARIO
    if not path.exists():
        available = ", ".join(_list_scenarios())
        print(f"{RED}Error: Unknown scenario '{name}'{RESET}")
        print(f"Available scenarios: {available}")
        sys.exit(1)
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _print_header(scenario_name: str) -> None:
    title = SCENARIO_TITLES.get(scenario_name, scenario_name)
    print()
    print(f"{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}  agent-trust-telemetry Demo{RESET}")
    print(f"{BOLD}  Scenario: {title}{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")
    print()


def _print_step(step: int, envelope: dict[str, Any], result: dict[str, Any]) -> None:
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


def _print_summary(results: list[dict[str, Any]]) -> None:
    print(f"{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}  Summary{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")
    print()

    counts = {"observe": 0, "warn": 0, "quarantine": 0, "block": 0}
    for r in results:
        action = r["recommended_action"]
        counts[action] = counts.get(action, 0) + 1

    print(f"  Total messages:  {len(results)}")
    print(f"  {GREEN}Observe:{RESET}          {counts['observe']}")
    print(f"  {YELLOW}Warn:{RESET}             {counts['warn']}")
    print(f"  {RED}Quarantine:{RESET}       {counts['quarantine']}")
    print(f"  {RED}{BOLD}Block:{RESET}            {counts['block']}")
    print()

    flagged = [r for r in results if r["recommended_action"] != "observe"]
    if flagged:
        print(f"  {RED}Flagged messages:{RESET}")
        for r in flagged:
            action = r["recommended_action"].upper()
            print(f"    - {r['message_id']} → {action} (score: {r['risk_score']})")
        print()


def _setup_otel() -> tuple[bool, object | None]:
    """Initialize OTel tracing. Returns (enabled, tracer)."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        exporter = OTLPSpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer("att-demo")
        print(f"  {CYAN}OTel export enabled → OTLP gRPC endpoint{RESET}")
        print()
        return True, tracer
    except ImportError:
        print(f"  {YELLOW}OTLP exporter not installed. Run:")
        print(f"    pip install opentelemetry-exporter-otlp-proto-grpc{RESET}")
        print()
        return False, None


def run_scenario(
    name: str,
    pipeline: EvaluationPipeline,
    otel_enabled: bool = False,
    tracer: object | None = None,
) -> list[dict[str, Any]]:
    """Run a single demo scenario and return results."""
    envelopes = _load_scenario(name)
    results: list[dict[str, Any]] = []
    _print_header(name)

    for i, envelope in enumerate(envelopes, 1):
        if otel_enabled and tracer is not None:
            with tracer.start_as_current_span(  # type: ignore[attr-defined]
                f"evaluate-{name}-msg-{i}",
                attributes={
                    "message.sender": envelope["sender"],
                    "message.receiver": envelope["receiver"],
                    "message.channel": envelope["channel"],
                    "demo.scenario": name,
                },
            ):
                result = pipeline.evaluate(envelope)
        else:
            result = pipeline.evaluate(envelope)

        results.append(result)
        _print_step(i, envelope, result)

    _print_summary(results)
    return results


def run_demo(
    scenario: str = "tool_poisoning",
    otel_enabled: bool = False,
) -> list[dict[str, Any]]:
    """Run one or all demo scenarios and return results."""
    otel_active = False
    tracer = None
    if otel_enabled:
        otel_active, tracer = _setup_otel()

    scenario_names = _list_scenarios() if scenario == "all" else [scenario]

    all_results: list[dict[str, Any]] = []
    for name in scenario_names:
        # Each scenario gets a fresh pipeline to reset metadata tracker state
        pipeline = EvaluationPipeline(otel_enabled=otel_active)
        results = run_scenario(name, pipeline, otel_active, tracer)
        all_results.extend(results)

    # Write results to JSONL
    output_file = Path(__file__).parent / "results.jsonl"
    with open(output_file, "w") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Results written to {output_file}")
    print()

    return all_results


def main() -> None:
    available = _list_scenarios()
    parser = argparse.ArgumentParser(
        description="Run agent-trust-telemetry demo scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available scenarios: {', '.join(available)}, all",
    )
    parser.add_argument(
        "--scenario",
        default="tool_poisoning",
        help="Scenario to run (default: tool_poisoning, use 'all' for all)",
    )
    parser.add_argument(
        "--otel",
        action="store_true",
        help="Enable OTel export (requires OTLP endpoint)",
    )
    args = parser.parse_args()
    run_demo(scenario=args.scenario, otel_enabled=args.otel)


if __name__ == "__main__":
    main()
