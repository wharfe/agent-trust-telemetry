"""CLI entry point for agent-trust-telemetry.

Commands:
    att evaluate --message FILE    Evaluate a single message JSON file
    att evaluate --stream FILE     Evaluate a JSONL stream
    att report --input FILE        Display evaluation results as a table
    att quarantine list            List quarantined messages (demo only)
    att quarantine release --message-id ID  Release a quarantined message
    att quarantine clear           Clear all quarantined messages
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from att.pipeline import EvaluationPipeline

# In-memory quarantine list (demo only, not for production)
_quarantine_list: dict[str, dict[str, Any]] = {}


def _evaluate_message(pipeline: EvaluationPipeline, filepath: str) -> None:
    """Evaluate a single message JSON file."""
    with open(filepath) as f:
        envelope = json.load(f)
    result = pipeline.evaluate(envelope)

    # Track quarantine
    if result["recommended_action"] == "quarantine":
        _quarantine_list[result["message_id"]] = result

    print(json.dumps(result, indent=2, ensure_ascii=False))


def _evaluate_stream(pipeline: EvaluationPipeline, filepath: str) -> None:
    """Evaluate a JSONL stream file."""
    if filepath == "-":
        _process_stream(pipeline, sys.stdin)
    else:
        with open(filepath) as f:
            _process_stream(pipeline, f)


def _process_stream(pipeline: EvaluationPipeline, source: Any) -> None:
    """Process lines from a stream source."""
    for line in source:
        line = line.strip()
        if not line:
            continue
        envelope = json.loads(line)
        result = pipeline.evaluate(envelope)

        if result["recommended_action"] == "quarantine":
            _quarantine_list[result["message_id"]] = result

        print(json.dumps(result, ensure_ascii=False))


def _report(filepath: str, fmt: str) -> None:
    """Display evaluation results."""
    results: list[dict[str, Any]] = []
    if filepath == "-":
        for line in sys.stdin:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    else:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))

    if fmt == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    # Table format
    if not results:
        print("No evaluation results found.")
        return

    header = f"{'message_id':<50} {'score':>5} {'severity':<8} {'action':<12} {'classes'}"
    print(header)
    print("-" * len(header))
    for r in results:
        msg_id = r.get("message_id", "")[:48]
        score = r.get("risk_score", 0)
        severity = r.get("severity", "")
        action = r.get("recommended_action", "")
        classes = ", ".join(
            pc.get("name", "") for pc in r.get("policy_classes", [])
        )
        indicators = ", ".join(
            ai.get("name", "") for ai in r.get("anomaly_indicators", [])
        )
        all_findings = ", ".join(filter(None, [classes, indicators])) or "-"
        print(f"{msg_id:<50} {score:>5} {severity:<8} {action:<12} {all_findings}")


def _quarantine_cmd(args: argparse.Namespace) -> None:
    """Handle quarantine subcommands (demo only)."""
    if args.quarantine_action == "list":
        if not _quarantine_list:
            print("No quarantined messages.")
            return
        for msg_id, result in _quarantine_list.items():
            print(
                f"  {msg_id}  score={result['risk_score']}  "
                f"severity={result['severity']}  action={result['recommended_action']}"
            )
    elif args.quarantine_action == "release":
        msg_id = args.message_id
        if msg_id in _quarantine_list:
            del _quarantine_list[msg_id]
            print(f"Released: {msg_id}")
        else:
            print(f"Not found in quarantine: {msg_id}", file=sys.stderr)
            sys.exit(1)
    elif args.quarantine_action == "clear":
        count = len(_quarantine_list)
        _quarantine_list.clear()
        print(f"Cleared {count} quarantined message(s).")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="att",
        description="agent-trust-telemetry: trust telemetry for inter-agent communication",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate messages")
    eval_group = eval_parser.add_mutually_exclusive_group(required=True)
    eval_group.add_argument("--message", metavar="FILE", help="Single message JSON file")
    eval_group.add_argument(
        "--stream", metavar="FILE", help="JSONL stream file (use '-' for stdin)"
    )
    eval_parser.add_argument(
        "--rules-dir",
        metavar="DIR",
        default=None,
        help="Custom rules directory (default: builtin rules)",
    )
    eval_parser.add_argument(
        "--otel",
        action="store_true",
        default=False,
        help="Enable OpenTelemetry export (requires otel extras)",
    )

    # report
    report_parser = subparsers.add_parser("report", help="Display evaluation results")
    report_parser.add_argument(
        "--input", metavar="FILE", required=True, help="Evaluation results JSONL file"
    )
    report_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        dest="fmt",
        help="Output format (default: table)",
    )

    # quarantine
    q_parser = subparsers.add_parser(
        "quarantine", help="Manage quarantined messages (demo only)"
    )
    q_sub = q_parser.add_subparsers(dest="quarantine_action")
    q_sub.add_parser("list", help="List quarantined messages")
    release_parser = q_sub.add_parser("release", help="Release a quarantined message")
    release_parser.add_argument("--message-id", required=True, help="Message ID to release")
    q_sub.add_parser("clear", help="Clear all quarantined messages")

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "evaluate":
        rules_dir = Path(args.rules_dir) if args.rules_dir else None
        pipeline = EvaluationPipeline(rules_dir=rules_dir, otel_enabled=args.otel)
        if args.message:
            _evaluate_message(pipeline, args.message)
        else:
            _evaluate_stream(pipeline, args.stream)

    elif args.command == "report":
        _report(args.input, args.fmt)

    elif args.command == "quarantine":
        if args.quarantine_action is None:
            parser.parse_args(["quarantine", "--help"])
        else:
            _quarantine_cmd(args)


if __name__ == "__main__":
    main()
