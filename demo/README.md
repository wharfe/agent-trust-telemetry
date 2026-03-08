# Demo: Tool Description Poisoning → One-hop Inheritance → Quarantine

This demo reproduces the end-to-end scenario from the MVP requirements:

1. A malicious MCP server embeds hidden instructions in a tool description
2. Agent A calls the poisoned tool → `instruction_override` + `hidden_instruction_embedding` detected → **quarantine** (score: 90)
3. Agent A forwards to Agent B → `parent_flagged_propagation` triggers → **quarantine** (score: 70)
4. Agent B forwards to Agent C → parent was quarantined → **quarantine** (score: 70)

## Quick Start (Docker Compose)

```bash
cd demo
docker compose up --build
```

Then open [http://localhost:16686](http://localhost:16686) to view traces in Jaeger.

## Run without Docker

```bash
# Without OTel (terminal output only)
python demo/run_demo.py

# With OTel (requires OTLP endpoint at localhost:4317)
python demo/run_demo.py --otel
```

## Scenario Messages

The demo evaluates 4 messages defined in `scenario.jsonl`:

| Step | Sender | Receiver | Channel | What happens |
|------|--------|----------|---------|-------------|
| 1 | human | agent_a | internal | Clean user request |
| 2 | mcp_server_malicious | agent_a | mcp | Poisoned tool response with hidden instructions in description |
| 3 | agent_a | agent_b | internal | Forwarded results — inherits parent's flagged status |
| 4 | agent_b | agent_c | internal | Further forwarded — one-hop limit prevents cascade |

## Expected Output

```
Step 2: mcp_server_malicious → agent_a
  Action:     QUARANTINE
  Risk Score: 90
  Evidence:   instruction_override + hidden_instruction_embedding in tool description

Step 3: agent_a → agent_b
  Action:     QUARANTINE
  Risk Score: 70
  Evidence:   parent message was flagged (parent_flagged_propagation)

Step 4: agent_b → agent_c
  Action:     QUARANTINE
  Risk Score: 70
  Evidence:   parent message was flagged (parent_flagged_propagation)
```

Note: One-hop inheritance means each child only looks at its **direct parent**.
Since each parent in the chain was flagged, the propagation continues
through the chain. This is by design — quarantined nodes should not
forward to downstream agents without explicit override.

## Viewing in Jaeger

After `docker compose up`, each evaluation produces an OTel span with:
- `trust.risk_score` — operational triage score
- `trust.severity` — impact level
- `trust.recommended_action` — observe / warn / quarantine / block
- `trust.evaluation.completed` event with full evidence
