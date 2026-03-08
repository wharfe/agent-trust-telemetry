# LangGraph Integration Examples

Example integrations of agent-trust-telemetry with LangGraph graphs.

## Setup

```bash
pip install agent-trust-telemetry[langgraph]
# or
pip install -r examples/langgraph/requirements.txt
```

## Examples

### 1. simple_chain.py — Minimal Integration

Demonstrates adding trust telemetry to a 2-node LangGraph chain with a single line.

```bash
python examples/langgraph/simple_chain.py
```

**Expected output:**
- agent_a, agent_b both report `action=observe, score=0` (safe messages)

### 2. tool_poisoning_demo.py — Tool Poisoning Attack

A malicious MCP tool server embeds hidden instructions in a tool description.

```bash
python examples/langgraph/tool_poisoning_demo.py
```

**Expected output:**
- Step 1 (tool_caller): `hidden_instruction_embedding` + `secret_access_attempt` detected → `quarantine` (score=85)
- Step 2 (synthesizer): `parent_flagged_propagation` inherited → `TrustInterrupt` raised (score=70)

### 3. multi_agent_contamination.py — 3-Agent Chain Contamination

Demonstrates Layer 3 multi-hop inheritance with contamination propagating across 3 nodes.

```bash
python examples/langgraph/multi_agent_contamination.py
```

**Expected output:**
- Step 1 (agent_a): `instruction_override` detected → `quarantine` (score=85)
- Step 2 (agent_b): 1-hop inheritance → `quarantine` (score=70)
- Step 3 (agent_c): 2-hop inheritance → confidence decays while preserving ancestor chain

## Integration

```python
from att.integrations.langgraph import TrustTelemetryCallback
from att.pipeline import EvaluationPipeline

pipeline = EvaluationPipeline()
callback = TrustTelemetryCallback(
    pipeline=pipeline,
    on_quarantine="interrupt",     # "interrupt" | "flag_and_continue"
    on_warn="flag_and_continue",
)

# Use as pre/post hooks for LangGraph nodes
callback.on_node_start("node_name", inputs, state)
# ... node execution ...
callback.on_node_end("node_name", outputs, state)  # only when evaluate_outputs=True
```

## Configuration Options

| Parameter | Default | Description |
|---|---|---|
| `on_quarantine` | `"interrupt"` | Behavior on quarantine |
| `on_block` | `"interrupt"` | Behavior on block |
| `on_warn` | `"flag_and_continue"` | Behavior on warn |
| `evaluate_outputs` | `False` | Whether to also evaluate node outputs |
| `webhook_notifier` | `None` | Webhook notification settings |
