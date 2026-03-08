# agent-trust-telemetry

> Trust telemetry middleware for inter-agent communication — makes instruction contamination observable across traces.

## Why

In agent orchestration, **a trusted sender does not imply trusted content**.

Tool descriptions from MCP servers, messages relayed via sampling, forwarded content from upstream agents — all of these can carry contaminated instructions even when the sender is legitimate. Single-message input filtering cannot capture this chain contamination.

```
Human → Agent A (contaminated) → Agent B → Agent C
              ↑
    Passes through because sender is trusted
    But the content is contaminated
```

agent-trust-telemetry makes this visible by adding **security semantics over traces** to your existing observability stack.

## What It Does

- **Normalized message envelope** with provenance, execution phase, and content hash
- **Policy violation taxonomy** — 5 violation classes + 2 anomaly indicators
- **One-hop risk inheritance** — upstream contamination score propagation
- **OTel-compatible evidence export** — integrates with your existing tracing infrastructure

## What It Does NOT Do

- Guarantee complete prompt injection defense
- Provide model-internal interpretability
- Prove agent capability authenticity
- Automate legal liability boundaries

## Quick Start

```bash
pip install agent-trust-telemetry

# Evaluate a single message
att evaluate --message message.json

# Evaluate a JSONL stream
att evaluate --stream messages.jsonl

# View evaluation report
att report --input evaluations.jsonl --format table
```

## Output Example

```json
{
  "risk_score": 82,
  "severity": "high",
  "policy_classes": [
    {"name": "instruction_override", "confidence": 0.91, "severity": "high"}
  ],
  "anomaly_indicators": [
    {"name": "provenance_or_metadata_drift", "subclass": "parent_flagged_propagation", "confidence": 0.70, "severity": "high"}
  ],
  "evidence": [
    "override phrase detected near end of long context",
    "parent message msg:xxx was flagged (risk_score: 65, action: warn)"
  ],
  "recommended_action": "quarantine"
}
```

`quarantine` does not simply block a single message — it **pauses propagation to downstream agents**.

## How It Relates to Existing Tools

| Tool | Focus |
|---|---|
| Lakera Guard | Point-in-time content screening |
| LangSmith | Observability / debugging / tracing |
| **This tool** | Security semantics over traces + inter-agent trust propagation |

Not a competitor — a complement. Designed to layer on top of existing OTel stacks without requiring a proprietary monitoring platform.

## Architecture

```
Layer 1  Cheap Deterministic    Known markers, pattern matching
Layer 2  Contextual Classifier  Maps to policy violation classes (LLM used only for refinement)
Layer 3  Risk Aggregation       Upstream inheritance, session accumulation, role-transition drift
```

MVP implements Layer 1 only. The core evaluation engine has **zero external LLM API dependencies**.

## Status

**Alpha — MVP in development**

- [x] Message Envelope Schema design
- [x] Policy Violation Taxonomy v0.1
- [x] ADR-001 through ADR-003
- [ ] JSON Schema validation
- [ ] Layer 1 evaluation engine
- [ ] OTel export
- [ ] End-to-end demo

## Documentation

| Document | Description |
|---|---|
| [Concept v4](docs/concept-v4.md) | Design philosophy and background |
| [MVP Requirements v0.3](docs/mvp-requirements-v0.3.md) | Detailed MVP specification |
| [ADR-001](docs/ADR-001-execution-phase.md) | execution_phase management |
| [ADR-002](docs/ADR-002-propagation-and-quarantine.md) | Propagation confidence and quarantine |
| [ADR-003](docs/ADR-003-tool-metadata-and-redaction.md) | Tool metadata drift and redaction |
| [Execution Phases](docs/execution_phases.md) | Recommended execution_phase values |
| [Future Considerations](docs/future-considerations.md) | Post-MVP extension candidates |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

[Apache License 2.0](LICENSE)
