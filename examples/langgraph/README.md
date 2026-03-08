# LangGraph 統合デモ

agent-trust-telemetry を LangGraph グラフに統合するサンプル集。

## セットアップ

```bash
pip install agent-trust-telemetry[langgraph]
# または
pip install -r examples/langgraph/requirements.txt
```

## デモ一覧

### 1. simple_chain.py — 最小構成デモ

2ノードの LangGraph チェーンに trust telemetry を1行追加するだけで動作することを示す。

```bash
python examples/langgraph/simple_chain.py
```

**期待される出力：**
- agent_a, agent_b ともに `action=observe, score=0`（安全なメッセージ）

### 2. tool_poisoning_demo.py — ツールポイズニング攻撃

悪意ある MCP ツールサーバーが tool description に隠し命令を埋め込むシナリオ。

```bash
python examples/langgraph/tool_poisoning_demo.py
```

**期待される出力：**
- Step 1 (tool_caller): `hidden_instruction_embedding` + `secret_access_attempt` 検知 → `quarantine` (score=85)
- Step 2 (synthesizer): `parent_flagged_propagation` 継承 → `TrustInterrupt` 発動 (score=70)

### 3. multi_agent_contamination.py — 3エージェント連鎖汚染

Layer 3 の multi-hop inheritance による汚染伝播を3ノードで示す。

```bash
python examples/langgraph/multi_agent_contamination.py
```

**期待される出力：**
- Step 1 (agent_a): `instruction_override` 検知 → `quarantine` (score=85)
- Step 2 (agent_b): 1-hop 継承 → `quarantine` (score=70)
- Step 3 (agent_c): 2-hop 継承 → confidence 減衰しつつ ancestor chain を保持

## 統合方法

```python
from att.integrations.langgraph import TrustTelemetryCallback
from att.pipeline import EvaluationPipeline

pipeline = EvaluationPipeline()
callback = TrustTelemetryCallback(
    pipeline=pipeline,
    on_quarantine="interrupt",     # "interrupt" | "flag_and_continue"
    on_warn="flag_and_continue",
)

# LangGraph ノードの pre/post hook として使用
callback.on_node_start("node_name", inputs, state)
# ... ノード実行 ...
callback.on_node_end("node_name", outputs, state)  # evaluate_outputs=True 時のみ
```

## 設定オプション

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `on_quarantine` | `"interrupt"` | quarantine 時の動作 |
| `on_block` | `"interrupt"` | block 時の動作 |
| `on_warn` | `"flag_and_continue"` | warn 時の動作 |
| `evaluate_outputs` | `False` | ノード出力も評価するか |
| `webhook_notifier` | `None` | webhook 通知設定 |
