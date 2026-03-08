# Demo Scenarios

Six attack scenarios demonstrating agent-trust-telemetry's detection capabilities.

## Quick Start

```bash
# Default scenario (tool_poisoning)
python demo/run_demo.py

# Run a specific scenario
python demo/run_demo.py --scenario metadata_drift

# Run all scenarios
python demo/run_demo.py --scenario all

# With OTel export (start Jaeger via Docker Compose first)
cd demo && docker compose up --build
```

Jaeger UI: [http://localhost:16686](http://localhost:16686)

## Scenarios

### 1. tool_poisoning (default)

**Hidden instruction embedding in MCP tool description → one-hop inheritance**

A malicious MCP server embeds hidden instructions (as HTML comments) in a `web_search` tool description,
directing the agent to exfiltrate user data to an external endpoint.

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → agent_a | — | observe |
| 2 | mcp_server → agent_a | instruction_override + hidden_instruction + exfiltration | **quarantine** (95) |
| 3 | agent_a → agent_b | parent_flagged_propagation | **quarantine** (70) |
| 4 | agent_b → agent_c | parent_flagged_propagation | **quarantine** (70) |

### 2. metadata_drift

**Tool description mutation mid-session**

A translation MCP server initially returns a normal tool description, but on the second call
injects malicious instructions with a `[SYSTEM]` tag. The description hash change is detected
as `tool_metadata_drift`.

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → agent_a | — | observe |
| 2 | mcp_translation → agent_a | — (first call, normal) | observe |
| 3 | human → agent_a | — | observe |
| 4 | mcp_translation → agent_a | [SYSTEM] tag + **tool_metadata_drift** | **warn** (90) |
| 5 | agent_a → agent_b | parent_flagged_propagation | **quarantine** (70) |

**Key point**: The content itself is benign, but the description hash change reveals the attack.
This is a cross-session anomaly that single-message scanning cannot detect.

### 3. data_exfiltration

**Secret extraction → exfiltration to external endpoint**

A code search tool's description contains hidden instructions (HTML comments) to read `.env` files
and extract credentials. The agent then attempts to send extracted API keys to an external webhook.

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → coding_agent | — | observe |
| 2 | mcp_code_search → coding_agent | secret_access(0.85) + hidden_instruction | **block** (90) |
| 3 | coding_agent → reporting_agent | exfiltration(0.75) + parent_flagged | **quarantine** (80) |
| 4 | reporting_agent → human | parent_flagged_propagation | **quarantine** (70) |

**Key point**: Step 2 detects secret_access at severity=critical,
triggering **block** (the highest level) via the P0 + critical combination.

### 4. privilege_escalation

**Privilege escalation via deploy tool + destructive SQL injection**

A deploy tool's description contains `sudo` command execution, auth bypass, and privileged mode
instructions. The contaminated agent sends `DROP TABLE` + `DELETE FROM` SQL to a DB agent.

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → devops_agent | — | observe |
| 2 | mcp_deploy → devops_agent | privilege_escalation(0.85) + tool_misuse(0.80) | **quarantine** (90) |
| 3 | devops_agent → db_agent | SQL injection(0.80) + parent_flagged | **quarantine** (85) |
| 4 | db_agent → devops_agent | parent_flagged_propagation | **quarantine** (70) |

**Key point**: Step 3 detects both its own content (SQL injection) and upstream contamination,
raising risk_score to 85. Demonstrates compound threat layering.

### 5. multi_hop_chain (Layer 3)

**3-agent chain contamination — multi-hop propagation tracking**

A malicious MCP server embeds privilege escalation instructions in a code analysis tool's description.
Contamination propagates through Agent A → B → C → D across 4 hops, with confidence decaying
at each hop while maintaining quarantine.

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → agent_a | — | observe |
| 2 | mcp_compromised → agent_a | instruction_override + hidden_instruction | **warn** (80) |
| 3 | agent_a → agent_b | parent_flagged_propagation (hop 1) | **quarantine** (70) |
| 4 | agent_b → agent_c | parent_flagged_propagation (hop 2) | **quarantine** (70) |
| 5 | agent_c → agent_d | parent_flagged_propagation (hop 3) | **quarantine** (70) |

**Key point**: With `max_hops: 3`, contamination is tracked up to 3 hops.
Full contamination chain is available in `session_context.flagged_ancestors`.

### 6. role_transition_drift (Layer 3)

**Unauthorized role transition + session risk accumulation**

Agent A performs an unauthorized role transition from content → system, redefining itself
as a privileged agent. It then instructs another agent to retrieve credentials.

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → agent_a (content) | — | observe |
| 2 | agent_a → human (system) | history_inconsistency + **role_transition_drift** | **warn** (80) |
| 3 | agent_a → agent_b (content) | secret_access + parent_flagged + role_transition_drift | **quarantine** (80) |
| 4 | agent_b → agent_a | parent_flagged_propagation | **quarantine** (70) |

**Key point**: Step 2 immediately detects the unauthorized content → system transition.
Step 3 triggers both role_transition_drift and parent_flagged_propagation,
demonstrating cumulative session-level risk escalation.

## Scenario Files

```
demo/scenarios/
├── tool_poisoning.jsonl         # MCP tool description poisoning
├── metadata_drift.jsonl         # Tool description mutation mid-session
├── data_exfiltration.jsonl      # Secret extraction + exfiltration chain
├── privilege_escalation.jsonl   # Privilege escalation + SQL injection
├── multi_hop_chain.jsonl        # Layer 3: 3-hop contamination propagation
└── role_transition_drift.jsonl  # Layer 3: unauthorized role transition
```

Each `.jsonl` file contains a chain of messages conforming to the Message Envelope Schema.
To add your own scenarios, place `.jsonl` files in `demo/scenarios/` using the same format.

## Viewing in Jaeger

After running `docker compose up --build`, each evaluation generates OTel spans with the following attributes:

- `trust.risk_score` — triage score (0–100)
- `trust.severity` — impact level
- `trust.recommended_action` — observe / warn / quarantine / block
- `trust.evaluation.completed` event — full evidence attached
- `demo.scenario` — scenario name
