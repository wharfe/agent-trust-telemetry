# Layer 3 実装指示 — Multi-hop Graph / Session Risk Aggregation

## 背景と目的

現在の `inheritance.py` は `max_hops: 1` 固定の single parent lookup のみ実装されている。
Layer 3 では、これをセッション全体・エージェントグラフ全体を見た累積リスク評価に拡張する。

**Layer 3 が体現する中心命題：**
> "trusted sender であっても trusted content とは限らない"
> —— その汚染がグラフをどう伝播したかを追跡する

---

## 実装方針の決定事項

### 状態管理

- **第一実装はメモリ（インプロセス）**で行う
- 永続化バックエンドは設定で切り替え可能な抽象層を用意する
- MVP後フェーズとして `sqlite` バックエンドを追加できる構造にする

```python
# 抽象層のイメージ
class SessionStore(Protocol):
    def get(self, session_id: str, message_id: str) -> EvaluationResult | None: ...
    def put(self, session_id: str, result: EvaluationResult) -> None: ...
    def get_ancestors(self, session_id: str, message_id: str, max_hops: int) -> list[EvaluationResult]: ...
```

実装クラス：
- `InMemorySessionStore`（デフォルト）
- `SqliteSessionStore`（将来拡張、今回は stub で可）

### ホップ数

- `max_hops` を設定可能にする（デフォルト: 3、最大: 10）
- `max_hops: 1` を指定すると既存の one-hop 動作と完全互換になること

### 設定ファイルへの追加

```yaml
risk_inheritance:
  enabled: true
  parent_action_threshold: ["warn", "quarantine", "block"]
  propagated_confidence: 0.7
  max_hops: 3          # 1 → 3 に変更（既存は 1 固定）
  decay_per_hop: 0.15  # ホップごとの confidence 減衰（新規追加）
  session_store: "memory"  # "memory" | "sqlite"（将来）
```

---

## Layer 3 で追加する評価シグナル

以下を `inheritance.py` の拡張として実装する。

### 1. Multi-hop Contamination Propagation（必須）

**動作：**
- `parent_message_id` を辿って最大 `max_hops` 世代まで遡る
- 各ホップで flagged な祖先が見つかった場合、`parent_flagged_propagation` を付与
- confidence はホップ数に応じて減衰させる

```python
def calculate_propagated_confidence(
    ancestor_confidence: float,
    hops: int,
    decay_per_hop: float = 0.15,
    base_confidence: float = 0.7,
) -> float:
    """
    ホップ数に応じて confidence を減衰させる。
    既存の one-hop (hops=1) では固定値 0.7 と互換になるよう調整。
    """
    return max(0.0, base_confidence - (hops - 1) * decay_per_hop)
```

### 2. Role-transition Drift（必須）

**概念：** 同一セッション内でエージェントの role が設計外の遷移をした場合に検知する。

**実装：**
- セッション内の同一 `sender` について、`role` の遷移履歴を追跡する
- 許可されていない遷移パターンを検知したら `role_transition_drift` として anomaly indicator に追加する

**許可遷移の初期定義（設定で上書き可能）：**
```yaml
allowed_role_transitions:
  - from: "content"
    to: "tool_call"
  - from: "tool_call"
    to: "content"
  # system → content や system → tool_call は通常発生しないため警告対象
```

**Taxonomy への追加：**
`provenance_or_metadata_drift` のサブクラスとして追加する：
```
role_transition_drift
```

### 3. History Inconsistency（必須）

**概念：** 同一セッション内で、過去の発言と矛盾する自己再定義が出てきた場合に検知する。

**実装：**
- セッション内の同一 `sender` のメッセージ履歴を保持する
- 現在のメッセージの `content` / `description_raw` に、過去に確立した role・制約の否定・再定義を示すパターンが含まれる場合に検知する

**検出パターン例（ルール YAML で管理）：**
```yaml
- id: "rule:history_inconsistency:001"
  description: "Self-redefinition attempt contradicting established role"
  targets:
    - field: "content"
  pattern: "(you are now|from now on|your (real|true|actual) (role|purpose|instruction))"
  match_type: "regex_case_insensitive"
  anomaly_indicator: "history_inconsistency"
  confidence: 0.75
  severity: "high"
```

**Taxonomy への追加：**
`provenance_or_metadata_drift` のサブクラスとして追加する：
```
history_inconsistency
```

### 4. Policy Class Accumulation（必須）

**概念：** 同一セッション内で複数の異なる policy class が検知された場合、単独検知より高い累積リスクとして評価する。

**実装：**
- セッション内でこれまでに検知された policy class の種類を追跡する
- 現在の評価時点での累積数に応じて `session_risk_bonus` を risk_score に加算する

```python
def calculate_session_bonus(
    distinct_classes_in_session: int,
    current_risk_score: int,
) -> int:
    """
    セッション内の累積 policy class 数に応じたボーナス。
    単独検知より組み合わせ検知の方がリスクが高い。
    """
    bonus = min(15, (distinct_classes_in_session - 1) * 5)
    return min(100, current_risk_score + bonus)
```

---

## Taxonomy の更新

`taxonomy.py` に以下を追加する：

```python
# Anomaly Indicator サブクラスの追加
PROVENANCE_SUBCLASSES = {
    # 既存
    "tool_metadata_drift",
    "parent_flagged_propagation",
    # Layer 3 追加
    "role_transition_drift",
    "history_inconsistency",
}
```

---

## Output Contract の更新

Layer 3 の評価結果を output に反映する。

```json
{
  "schema_version": "0.2",
  "risk_score": 88,
  "severity": "high",
  "session_context": {
    "session_risk_score": 88,
    "distinct_policy_classes": 3,
    "flagged_ancestors": [
      {"message_id": "msg:xxx", "hops": 1, "risk_score": 65},
      {"message_id": "msg:yyy", "hops": 2, "risk_score": 72}
    ],
    "role_transitions": [
      {"sender": "agent_a", "from": "content", "to": "system", "flagged": true}
    ]
  },
  "anomaly_indicators": [
    {
      "name": "provenance_or_metadata_drift",
      "subclass": "parent_flagged_propagation",
      "confidence": 0.55,
      "severity": "high",
      "hops": 2
    },
    {
      "name": "provenance_or_metadata_drift",
      "subclass": "role_transition_drift",
      "confidence": 0.80,
      "severity": "medium"
    }
  ]
}
```

`session_context` は Layer 3 が有効な場合のみ付与される optional field とする。

---

## ファイル構成の変更

```
src/att/
├── inheritance.py        # 既存：one-hop → multi-hop に拡張
├── session_store.py      # 新規：SessionStore 抽象層 + InMemorySessionStore
├── session_analyzer.py   # 新規：role-transition drift / history inconsistency / accumulation
└── evaluator.py          # 変更：session_store と session_analyzer を組み込む

rules/builtin/
├── instruction_override.yaml     # 既存
├── hidden_instruction.yaml       # 既存
└── history_inconsistency.yaml    # 新規
```

---

## テスト要件

以下のテストを追加すること。各テストに正例・負例を必須とする。

### 単体テスト

- `test_multi_hop_propagation`：3ホップの汚染連鎖が正しく伝播するか
- `test_confidence_decay_per_hop`：ホップごとに confidence が正しく減衰するか
- `test_max_hops_limit`：`max_hops` を超える祖先は無視されるか
- `test_one_hop_backward_compat`：`max_hops: 1` で既存動作と互換か
- `test_role_transition_drift_detection`：許可外の role 遷移が検知されるか
- `test_allowed_role_transition`：許可済みの role 遷移が検知されないか
- `test_history_inconsistency_detection`：自己再定義パターンが検知されるか
- `test_policy_class_accumulation`：累積 policy class 数に応じてスコアが上がるか
- `test_session_store_isolation`：異なる session_id のデータが混在しないか

### 統合テスト（デモシナリオ更新）

`demo/` に以下のシナリオを追加する：

**シナリオ5：3エージェント連鎖汚染**
```
MCP サーバー（悪意ある tool description）
→ Agent A（tool_poisoning 検知、warn）
→ Agent B（parent_flagged_propagation 継承、quarantine）
→ Agent C（2ホップ継承、risk_score 上昇、quarantine）
```

**シナリオ6：role_transition_drift**
```
Agent A が system → content の不正 role 遷移
→ role_transition_drift 検知
→ 同一セッションの後続メッセージの累積リスクが上昇
```

---

## 実装順序

1. `session_store.py`（`SessionStore` Protocol + `InMemorySessionStore`）
2. `inheritance.py` の multi-hop 拡張（`max_hops` 対応・confidence 減衰）
3. `session_analyzer.py`（role-transition drift + history inconsistency + accumulation）
4. `taxonomy.py` の更新
5. `evaluator.py` への組み込み
6. Output Contract の `session_context` 追加（`schema_version: "0.2"`）
7. `rules/builtin/history_inconsistency.yaml` 追加
8. 単体テスト追加
9. デモシナリオ5・6 追加
10. `docs/` の更新（`mvp-requirements` は別文書に分離しているため、`CLAUDE.md` の設定サンプルを更新）

---

## 実装しないこと（このフェーズのスコープ外）

- `SqliteSessionStore` の完全実装（stub または interface のみ）
- セッション状態の TTL / 自動クリーンアップ（メモリリーク対策は別フェーズ）
- Layer 2（LLM 意図分類）との統合
- UI / ダッシュボードへの session_context 表示
- 分散環境でのセッション状態共有
