# LangGraph 統合実装指示

## 背景と目的

現在のデモはモックエージェントで動作している。
このフェーズでは **実際の LangGraph グラフに `att` を差し込み、実運用に近い形で動作することを示す**。

合わせて、quarantine 発動時のオーケストレーターへの通知（webhook）を
LangGraph の callback 機構を使って自然な形で実装する。

---

## 設計決定事項

### 統合形式

**pre/post hook 方式**を採用する。

LangGraph の `add_node` に渡す関数の前後に `att evaluate` を差し込む
`TrustTelemetryCallback` を実装する。

```python
# 利用者側のコードイメージ（これが目指すUX）
from att.integrations.langgraph import TrustTelemetryCallback

callback = TrustTelemetryCallback(config=att_config)

graph = StateGraph(AgentState)
graph.add_node("agent_a", agent_a_fn, callbacks=[callback])
graph.add_node("agent_b", agent_b_fn, callbacks=[callback])
```

既存グラフへの変更を最小限にする。**1行追加で有効になること**を体験の基準とする。

### quarantine 時の動作

設定で切り替え可能にする。デフォルトは `interrupt`。

```yaml
# att_config.yaml
langgraph:
  on_quarantine: "interrupt"   # "interrupt" | "flag_and_continue"
  on_warn: "flag_and_continue" # "interrupt" | "flag_and_continue"
```

- `interrupt`：`GraphInterrupt` を raise し、グラフの実行を中断する
- `flag_and_continue`：`state` に `trust_flags` を付与して実行を継続する

### デモの追加場所

既存の `demo/` は変更しない。
`examples/langgraph/` を新規作成し、LangGraph 専用サンプルを置く。

---

## ファイル構成

```
src/att/
└── integrations/
    ├── __init__.py
    └── langgraph/
        ├── __init__.py
        ├── callback.py        # TrustTelemetryCallback（メイン実装）
        ├── state.py           # TrustState（LangGraph state 拡張）
        ├── interrupt.py       # TrustInterrupt（GraphInterrupt サブクラス）
        └── webhook.py         # QuarantineWebhookNotifier

examples/langgraph/
├── README.md
├── requirements.txt           # langgraph, langchain-core 等
├── simple_chain.py            # 最小構成デモ（2ノード）
├── tool_poisoning_demo.py     # 既存デモの LangGraph 版
└── multi_agent_contamination.py  # 3エージェント連鎖汚染（Layer 3 連携）

tests/integrations/
└── langgraph/
    ├── test_callback.py
    ├── test_interrupt.py
    └── test_webhook.py
```

---

## 実装詳細

### 1. `TrustState`（state.py）

LangGraph の `TypedDict` state に trust 評価結果を付与するための拡張。

```python
from typing import TypedDict, Annotated
from att.models import EvaluationResult

class TrustState(TypedDict, total=False):
    """
    既存の AgentState に mix-in して使う。
    
    例：
        class MyState(AgentState, TrustState):
            pass
    """
    trust_last_result: EvaluationResult | None
    trust_session_flags: list[EvaluationResult]
    trust_quarantined: bool
```

### 2. `TrustInterrupt`（interrupt.py）

LangGraph の `GraphInterrupt` を継承し、評価結果を保持する。

```python
from langgraph.errors import GraphInterrupt
from att.models import EvaluationResult

class TrustInterrupt(GraphInterrupt):
    """
    quarantine / block 発動時に raise される。
    オーケストレーター側で catch して対応できる。
    
    例：
        try:
            graph.invoke(state)
        except TrustInterrupt as e:
            print(e.evaluation.recommended_action)  # "quarantine"
            print(e.evaluation.evidence)
    """
    def __init__(self, evaluation: EvaluationResult):
        self.evaluation = evaluation
        super().__init__(
            f"Trust telemetry interrupted: {evaluation.recommended_action} "
            f"(risk_score={evaluation.risk_score}, severity={evaluation.severity})"
        )
```

### 3. `TrustTelemetryCallback`（callback.py）

メインの実装。LangGraph の callback interface を実装する。

```python
class TrustTelemetryCallback:
    """
    LangGraph ノードの pre/post hook として att 評価を差し込む。

    設定：
        config (AttConfig): att の設定オブジェクト
        on_quarantine (str): "interrupt" | "flag_and_continue"
        on_warn (str): "interrupt" | "flag_and_continue"
        webhook_notifier (QuarantineWebhookNotifier | None): optional
    """

    def on_node_start(
        self,
        node_name: str,
        inputs: dict,
        state: TrustState,
        **kwargs,
    ) -> None:
        """
        ノード実行前に入力メッセージを評価する。
        
        - inputs から content / tool_context を抽出して Envelope を構築
        - att evaluate を実行
        - 結果を state["trust_last_result"] に書き込む
        - on_quarantine / on_warn に応じて TrustInterrupt を raise するか
          state["trust_quarantined"] = True を設定する
        """

    def on_node_end(
        self,
        node_name: str,
        outputs: dict,
        state: TrustState,
        **kwargs,
    ) -> None:
        """
        ノード実行後に出力メッセージを評価する（オプション）。
        on_node_start と同様の処理。
        デフォルトは無効（設定で有効化可能）。
        """
```

**Envelope 構築ロジック：**

LangGraph の inputs/outputs から att の `MessageEnvelope` を構築するマッピングが必要。
以下のルールで自動マッピングする：

```python
def _build_envelope_from_langgraph(
    node_name: str,
    inputs: dict,
    state: TrustState,
) -> MessageEnvelope:
    """
    LangGraph の入力から MessageEnvelope を構築する。
    
    マッピングルール：
    - sender: 直前のノード名（state の history から取得）
    - receiver: 現在のノード名
    - channel: "internal"（LangGraph 内部通信）
    - session_id: state.get("session_id") or 自動生成
    - parent_message_id: state.get("trust_last_result.message_id")
    - content: inputs.get("messages", [{}])[-1].get("content")
    - execution_phase: node_name をそのまま使用
    - provenance: state の history から sender chain を構築
    """
```

### 4. `QuarantineWebhookNotifier`（webhook.py）

quarantine / block 発動時に外部へ通知する。
TrustTelemetryCallback から呼び出される形で実装する。

```python
class QuarantineWebhookNotifier:
    """
    quarantine / block 発動時に webhook で通知する。
    
    設定：
        url (str): 通知先 URL
        actions (list[str]): 通知対象アクション（デフォルト: ["quarantine", "block"]）
        headers (dict): 追加ヘッダー（認証トークン等）
        timeout (float): タイムアウト秒数（デフォルト: 5.0）
        on_error (str): "ignore" | "raise"（デフォルト: "ignore"）
    """
    
    def notify(self, evaluation: EvaluationResult, node_name: str) -> None:
        """
        POST リクエストで評価結果を送信する。
        payload は output contract の JSON をそのまま使う。
        """
```

**設定例：**
```yaml
# att_config.yaml
langgraph:
  on_quarantine: "interrupt"
  on_warn: "flag_and_continue"
  webhook:
    url: "https://your-orchestrator/trust-events"
    actions: ["quarantine", "block"]
    headers:
      Authorization: "Bearer ${WEBHOOK_TOKEN}"
    timeout: 5.0
    on_error: "ignore"
```

---

## examples/langgraph/ の内容

### simple_chain.py（最小構成デモ）

2ノードの最小 LangGraph グラフに `TrustTelemetryCallback` を1行追加するだけで
動作することを示す。

```
Human → [node: agent_a] → [node: agent_b] → END
                 ↑
    TrustTelemetryCallback が pre/post hook で評価
```

### tool_poisoning_demo.py（既存デモの LangGraph 版）

`demo/` にある tool poisoning シナリオを LangGraph で再実装する。

```
MCP mock server（悪意ある tool description）
→ [node: tool_caller]   ← hidden_instruction_embedding 検知 → warn
→ [node: synthesizer]   ← parent_flagged_propagation 付与 → quarantine → TrustInterrupt
```

### multi_agent_contamination.py（3エージェント連鎖汚染）

Layer 3 の multi-hop 継承を LangGraph の実グラフで示す。

```
[node: agent_a]  ← tool poisoning → warn
    ↓
[node: agent_b]  ← 1-hop 継承 → quarantine → TrustInterrupt
    ↓（interrupt をキャッチして続行する場合）
[node: agent_c]  ← 2-hop 継承 → risk_score 上昇
```

---

## テスト要件

### 単体テスト（tests/integrations/langgraph/）

**test_callback.py：**
- `test_on_node_start_evaluates_input`：pre-hook が入力を評価するか
- `test_interrupt_on_quarantine`：`on_quarantine: "interrupt"` で `TrustInterrupt` が raise されるか
- `test_flag_and_continue_on_quarantine`：`flag_and_continue` で state に書き込まれるか
- `test_state_is_updated_with_result`：評価結果が `trust_last_result` に書き込まれるか
- `test_parent_message_id_propagation`：前ノードの評価 ID が次ノードの `parent_message_id` になるか

**test_interrupt.py：**
- `test_trust_interrupt_contains_evaluation`：`TrustInterrupt` が evaluation を保持するか
- `test_trust_interrupt_is_catchable`：`GraphInterrupt` として catch できるか

**test_webhook.py：**
- `test_webhook_notified_on_quarantine`：quarantine 時に POST が送信されるか
- `test_webhook_not_notified_on_warn`：warn のみの場合は送信されないか（デフォルト設定）
- `test_webhook_error_ignored_by_default`：通知失敗時に例外が伝播しないか
- `test_webhook_respects_action_filter`：`actions` 設定でフィルタリングされるか

---

## 実装順序

1. `TrustState`（state.py）
2. `TrustInterrupt`（interrupt.py）
3. `QuarantineWebhookNotifier`（webhook.py）
4. `TrustTelemetryCallback`（callback.py）— `on_node_start` のみ先に実装
5. 単体テスト追加（callback / interrupt / webhook）
6. `examples/langgraph/simple_chain.py`（動作確認用）
7. `on_node_end` の実装（callback.py）
8. `examples/langgraph/tool_poisoning_demo.py`
9. `examples/langgraph/multi_agent_contamination.py`
10. `examples/langgraph/README.md`

---

## 実装しないこと（このフェーズのスコープ外）

- CrewAI / AutoGen / Semantic Kernel 対応（LangGraph が安定してから）
- LangGraph の `CheckpointSaver` との統合（セッション永続化は別フェーズ）
- Layer 2（LLM 意図分類）との統合
- UI / ダッシュボードへの表示

---

## 依存関係

`pyproject.toml` に optional dependency として追加する：

```toml
[project.optional-dependencies]
langgraph = [
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
]
```

インストール：
```bash
pip install agent-trust-telemetry[langgraph]
```

コアの att は LangGraph なしで動作すること（既存の依存関係を汚染しない）。
