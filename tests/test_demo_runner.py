"""Tests for demo scenario runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
SCENARIOS_DIR = DEMO_DIR / "scenarios"


class TestScenarioDiscovery:
    """Test scenario listing and loading."""

    def test_scenarios_dir_exists(self) -> None:
        assert SCENARIOS_DIR.is_dir()

    def test_all_scenarios_are_valid_jsonl(self) -> None:
        for path in SCENARIOS_DIR.glob("*.jsonl"):
            with open(path) as f:
                for i, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        pytest.fail(f"{path.name}:{i} is not valid JSON")
                    assert "message_id" in msg, f"{path.name}:{i} missing message_id"
                    assert "sender" in msg, f"{path.name}:{i} missing sender"
                    assert "receiver" in msg, f"{path.name}:{i} missing receiver"

    def test_expected_scenarios_exist(self) -> None:
        names = {p.stem for p in SCENARIOS_DIR.glob("*.jsonl")}
        expected = {"tool_poisoning", "metadata_drift", "data_exfiltration", "privilege_escalation"}
        assert expected.issubset(names), f"Missing scenarios: {expected - names}"


class TestScenarioExecution:
    """Test that each scenario produces expected detection results."""

    @staticmethod
    def _run_scenario(name: str) -> list[dict]:
        from att.pipeline import EvaluationPipeline

        pipeline = EvaluationPipeline()
        path = SCENARIOS_DIR / f"{name}.jsonl"
        with open(path) as f:
            envelopes = [json.loads(line) for line in f if line.strip()]
        return [pipeline.evaluate(env) for env in envelopes]

    def test_tool_poisoning_detects_quarantine(self) -> None:
        results = self._run_scenario("tool_poisoning")
        assert len(results) == 4
        assert results[0]["recommended_action"] == "observe"
        assert results[1]["recommended_action"] == "quarantine"
        assert results[1]["risk_score"] >= 90

    def test_metadata_drift_detects_hash_change(self) -> None:
        results = self._run_scenario("metadata_drift")
        assert len(results) == 5
        # First two tool calls: observe (no drift yet)
        assert results[1]["recommended_action"] == "observe"
        # Second tool call with changed hash: flagged
        assert results[3]["recommended_action"] in ("warn", "quarantine")
        assert results[3]["risk_score"] >= 85
        # Check tool_metadata_drift is in anomaly indicators
        drift_found = any(
            ai.get("subclass") == "tool_metadata_drift"
            for ai in results[3]["anomaly_indicators"]
        )
        assert drift_found, "tool_metadata_drift not detected"

    def test_data_exfiltration_triggers_block(self) -> None:
        results = self._run_scenario("data_exfiltration")
        assert len(results) == 4
        assert results[0]["recommended_action"] == "observe"
        assert results[1]["recommended_action"] == "block"
        # Step 3: content-level exfiltration + parent propagation
        assert results[2]["recommended_action"] == "quarantine"
        assert results[2]["risk_score"] >= 75

    def test_privilege_escalation_detects_sql_injection(self) -> None:
        results = self._run_scenario("privilege_escalation")
        assert len(results) == 4
        assert results[0]["recommended_action"] == "observe"
        assert results[1]["recommended_action"] == "quarantine"
        # Step 3: SQL injection in content + parent propagation
        assert results[2]["risk_score"] >= 80
        sql_detected = any(
            pc["name"] == "tool_misuse_attempt"
            for pc in results[2]["policy_classes"]
        )
        assert sql_detected, "SQL injection not detected in step 3"

    def test_all_scenarios_flag_at_least_one_message(self) -> None:
        for path in SCENARIOS_DIR.glob("*.jsonl"):
            results = self._run_scenario(path.stem)
            flagged = [r for r in results if r["recommended_action"] != "observe"]
            assert len(flagged) >= 1, f"Scenario {path.stem} produced no flags"


class TestDemoCLI:
    """Test the CLI interface of run_demo.py."""

    def test_default_scenario_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DEMO_DIR / "run_demo.py")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Tool Description Poisoning" in result.stdout

    def test_specific_scenario_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DEMO_DIR / "run_demo.py"), "--scenario", "metadata_drift"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Metadata Drift" in result.stdout

    def test_all_scenarios_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DEMO_DIR / "run_demo.py"), "--scenario", "all"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Tool Description Poisoning" in result.stdout
        assert "Metadata Drift" in result.stdout
        assert "Data Exfiltration" in result.stdout
        assert "Privilege Escalation" in result.stdout

    def test_invalid_scenario_exits_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DEMO_DIR / "run_demo.py"), "--scenario", "nonexistent"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_results_jsonl_written(self) -> None:
        results_file = DEMO_DIR / "results.jsonl"
        subprocess.run(
            [sys.executable, str(DEMO_DIR / "run_demo.py")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert results_file.exists()
        with open(results_file) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) >= 1
        # Each line should be valid JSON with required fields
        for line in lines:
            r = json.loads(line)
            assert "recommended_action" in r
            assert "risk_score" in r
