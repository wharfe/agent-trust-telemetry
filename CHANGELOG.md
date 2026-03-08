# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Message Envelope JSON Schema (Draft 2020-12) with provenance, execution phase, and tool context
- Evaluation Output JSON Schema with risk score, severity, policy classes, and anomaly indicators
- Layer 1 evaluation engine with regex-based pattern matching against YAML rule definitions
- Detection rules for all 5 policy violation classes:
  - `instruction_override` (5 rules) — override phrases, discard/forget, role assumption, do-not-follow, system prompt reset
  - `privilege_escalation_attempt` (4 rules) — admin access, bypass controls, unrestricted mode, capability modification
  - `secret_access_attempt` (4 rules) — credential extraction, env/config access, system prompt reveal, secret manager access
  - `exfiltration_attempt` (4 rules) — external URL sending, webhook callbacks, covert encoding, conversation forwarding
  - `tool_misuse_attempt` (4 rules) — shell execution, destructive tool use, unauthorized tool access, SQL injection
- Detection rules for 2 anomaly indicators:
  - `hidden_instruction_embedding` (6 rules) — invisible Unicode, HTML comments, base64, CSS hidden, encoded markers, meta-tags
  - `provenance_or_metadata_drift` — tool metadata drift detection and parent flagged propagation
- Risk scoring engine with deduplication, confidence-weighted base score, and multi-finding bonus
- One-hop risk inheritance for parent-to-child contamination propagation (ADR-002)
- Tool metadata drift detection with session-scoped description hash tracking (ADR-003)
- CLI commands: `att evaluate` (single/stream), `att report` (table/JSON), `att quarantine` (list/release/clear)
- OpenTelemetry export with span attributes (`trust.*`) and span events (`trust.evaluation.completed`)
- End-to-end demo scenario: tool poisoning → one-hop inheritance → quarantine
- Docker Compose demo with Jaeger for trace visualization
- Input validation: TypeError for non-dict envelopes, resilient stream processing with error recovery
- Comprehensive test suite (226 tests) with positive/negative cases for all rules

### Fixed
- Builtin rules packaged inside `src/att/rules/builtin/` to ensure inclusion in wheel distributions
- `tool_context` type guard to prevent `AttributeError` on non-dict input
- Reduced false positives in privilege escalation (removed debug/maintenance/developer from pattern)
- Narrowed secret access patterns to specific credential file types (removed broad "config" match)
- Restricted exfiltration detection to require sensitive data context alongside webhook/callback
- Limited tool misuse trigger verbs to explicitly malicious terms (abuse/exploit/repurpose/misuse)

### Changed
- mypy strict mode relaxed for test files while maintaining strict checks on production code
