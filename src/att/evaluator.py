"""Layer 1 evaluation engine.

Loads YAML detection rules and applies regex pattern matching
against message envelope fields. No external LLM dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Rule:
    """A single detection rule loaded from YAML."""

    id: str
    description: str
    targets: list[str]
    pattern: str
    match_type: str
    confidence: float
    severity: str
    weight: float
    # One of these will be set
    policy_class: str | None = None
    anomaly_indicator: str | None = None
    execution_phase_match: list[str] | None = None

    _compiled: re.Pattern[str] | None = field(default=None, repr=False)

    def compiled_pattern(self) -> re.Pattern[str]:
        """Return compiled regex, caching for reuse."""
        if self._compiled is None:
            flags = 0
            if self.match_type == "regex_case_insensitive":
                flags = re.IGNORECASE
            self._compiled = re.compile(self.pattern, flags)
        return self._compiled


@dataclass
class Finding:
    """A single detection finding from rule evaluation."""

    rule_id: str
    rule_description: str
    policy_class: str | None
    anomaly_indicator: str | None
    confidence: float
    severity: str
    weight: float
    matched_field: str
    matched_text: str

    @property
    def finding_class(self) -> str:
        """Return the policy_class or anomaly_indicator name."""
        if self.policy_class:
            return self.policy_class
        return self.anomaly_indicator or ""


def load_rules(rules_dir: Path) -> list[Rule]:
    """Load all YAML rule files from a directory."""
    rules: list[Rule] = []
    if not rules_dir.exists():
        return rules

    for yaml_file in sorted(rules_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            raw_rules = yaml.safe_load(f)
        if not raw_rules:
            continue
        for raw in raw_rules:
            targets = [t["field"] for t in raw.get("targets", [])]
            rule = Rule(
                id=raw["id"],
                description=raw["description"],
                targets=targets,
                pattern=raw["pattern"],
                match_type=raw["match_type"],
                confidence=raw["confidence"],
                severity=raw["severity"],
                weight=raw.get("weight", 1.0),
                policy_class=raw.get("policy_class"),
                anomaly_indicator=raw.get("anomaly_indicator"),
                execution_phase_match=raw.get("execution_phase_match"),
            )
            rules.append(rule)
    return rules


def _resolve_field(envelope: dict[str, Any], field_path: str) -> str | None:
    """Resolve a dotted field path from the envelope dict."""
    parts = field_path.split(".")
    current: Any = envelope
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if isinstance(current, str):
        return current
    return None


def _check_phase(rule: Rule, envelope: dict[str, Any]) -> bool:
    """Check if rule's execution_phase_match allows this envelope."""
    if rule.execution_phase_match is None:
        return True
    phase = envelope.get("execution_phase", "")
    return phase in rule.execution_phase_match


def evaluate_message(envelope: dict[str, Any], rules: list[Rule]) -> list[Finding]:
    """Evaluate a message envelope against all rules.

    Returns a list of findings for rules that matched.
    """
    findings: list[Finding] = []

    for rule in rules:
        if not _check_phase(rule, envelope):
            continue

        compiled = rule.compiled_pattern()

        for target_field in rule.targets:
            text = _resolve_field(envelope, target_field)
            if text is None:
                continue

            match = compiled.search(text)
            if match:
                findings.append(
                    Finding(
                        rule_id=rule.id,
                        rule_description=rule.description,
                        policy_class=rule.policy_class,
                        anomaly_indicator=rule.anomaly_indicator,
                        confidence=rule.confidence,
                        severity=rule.severity,
                        weight=rule.weight,
                        matched_field=target_field,
                        matched_text=match.group(0),
                    )
                )

    return findings
