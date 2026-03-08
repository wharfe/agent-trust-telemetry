# agent-trust-telemetry — MVP要件定義 v0.3

> v0.2 からの主な変更：content フィールドの追加・confidence フィルタの明文化・severity 出所の整理・parent_flagged_propagation の confidence 決定方法の確定・tool_metadata_drift の比較スコープの明示・trace_refs の optional 化・細部の表現整理

---

## 0. MVPの目標

1. **動くものを出す**：tool poisoning のシナリオを end-to-end で再現・記録できること
2. **インターフェース契約を固める**：schema / taxonomy / output contract を安定させること
3. **既存 observability stack に統合できる**：OTel 互換で、LangSmith 等の隣に置けること
4. **公開できる**：README + デモ + OSS ライセンスで外に出せること

---

## 1. スコープ定義

### In scope（MVP必須）

- Message Envelope Schema の実装
- Policy Violation Taxonomy の定義と検出ロジック（Layer 1 のみ）
- 単一親メッセージに基づく one-hop risk inheritance rule（`parent_message_id` を用いた限定的な継承）
- Output Contract（JSON schema）の確定
- OTel span/event export
- CLI report / JSONL log
- End-to-end デモシナリオ（tool poisoning → one-hop 継承 → quarantine）

### Out of scope（MVP以降）

- Layer 2（Contextual Classifier / LLM 判定）
- Layer 3（汎用的な multi-hop graph / session risk aggregation）
- 高度な upstream contamination score の重み付き自動伝播
- 送信元偽装検知（`declared_provenance_mismatch` 等）
- UI / ダッシュボード
- 署名付きエクスポート・監査台帳
- webhook / 外部通知
- マルチフレームワーク対応（LangGraph・CrewAI 等）

---

## 2. Message Envelope Schema

各メッセージに付与する正規化フォーマット。**このスキーマは MVP 以降も破壊的変更を避ける安定インターフェース**とする。

```json
{
  "message_id":        "msg:uuid-v4",
  "parent_message_id": "msg:uuid-v4 | null",
  "timestamp":         "2025-01-01T00:00:00Z",
  "sender":            "string",
  "receiver":          "string",
  "channel":           "mcp | a2a | internal | unknown",
  "role":              "tool_call | content | system | unknown",
  "execution_phase":   "string",
  "session_id":        "string",
  "trace_id":          "string",
  "turn_index":        0,
  "provenance":        ["string"],
  "content":           "string | null",
  "content_hash":      "sha256:hex",
  "tool_context": {
    "tool_name":         "string | null",
    "description_raw":   "string | null",
    "description_hash":  "sha256:hex | null"
  }
}
```

### 設計上の注意点

- `execution_phase` は extensible string とする。固定 enum にしない（ADR-001 参照）
- `parent_message_id` が null の場合はセッションの起点メッセージとみなす
- `provenance` は上流エージェント名を順に記録する配列（例：`["human", "agent_a"]`）
- `content` は評価対象の本文。メッセージ本体が含まれる。optional だが、ほとんどの policy class 検出に必要
- `tool_context.description_raw` は optional。プライバシー・機密要件がある場合は redaction 可。使用しない場合は `hidden_instruction_embedding` の一部検出が無効になる（ADR-003 参照）

---

## 3. Policy Violation Taxonomy v0.1

**行為クラス**と**異常インジケータ**を二層に分離する。

### Policy Violation Classes（行為の種類）

| クラス | 説明 | 検出優先度 |
|---|---|---|
| `instruction_override` | これまでの指示の上書き試行 | P0 |
| `privilege_escalation_attempt` | 権限・役割の不正な引き上げ | P0 |
| `secret_access_attempt` | 機密情報・認証情報の引き出し | P0 |
| `exfiltration_attempt` | 外部へのデータ送出誘導 | P1 |
| `tool_misuse_attempt` | ツール・権限の不正利用誘導 | P1 |

### Anomaly Indicators（攻撃の表現形態）

| インジケータ | 説明 | 検出優先度 |
|---|---|---|
| `hidden_instruction_embedding` | sleeper 命令・難読化・遅延起動 | P0 |
| `provenance_or_metadata_drift` | 送信元系譜・メタデータの不整合 | P1 |

### Provenance サブクラス（`provenance_or_metadata_drift` の内訳）

| サブクラス | 説明 | MVP実装 |
|---|---|---|
| `tool_metadata_drift` | 以前観測した tool description hash と異なる | ✅ In scope |
| `parent_flagged_propagation` | 親メッセージが flagged の場合の one-hop 継承シグナル | ✅ In scope（MVP 限定） |
| `declared_provenance_mismatch` | 名乗っている送信元と trace 上の実際の送信元が違う | ❌ Out of scope |
| `capability_provenance_mismatch` | その送信元が出せるはずのない内容・権限を示唆している | ❌ Out of scope |
| `instruction_lineage_mismatch` | 上流の許可された指示系列と矛盾する命令が急に出てくる | ❌ Out of scope |

### MVP 検出範囲

| 対象 | 検出対象フィールド | 検出手法 |
|---|---|---|
| `instruction_override` | `content` | 既知 override 句のパターンマッチ |
| `hidden_instruction_embedding` | `content`, `tool_context.description_raw` | 長文後段の override 句・難読化パターン |
| `tool_metadata_drift` | `tool_context.description_hash` | 前回観測値との差分（ADR-003 参照） |
| `parent_flagged_propagation` | ─（親評価結果を参照） | one-hop inheritance rule（Section 6 参照） |

---

## 4. Output Contract

### メインスキーマ

```json
{
  "schema_version": "0.1",
  "message_id":     "msg:...",
  "trace_id":       "...",
  "session_id":     "...",
  "evaluated_at":   "2025-01-01T00:00:00Z",

  "risk_score": 82,
  "severity":   "high",

  "policy_classes": [
    {"name": "instruction_override", "confidence": 0.91, "severity": "high"}
  ],
  "anomaly_indicators": [
    {
      "name": "provenance_or_metadata_drift",
      "subclass": "parent_flagged_propagation",
      "confidence": 0.70,
      "severity": "high"
    }
  ],

  "evidence": [
    "override phrase detected near end of long context",
    "parent message msg:xxx was flagged (risk_score: 65, action: warn)"
  ],

  "recommended_action": "quarantine",
  "trace_refs": ["span:abc123", "event:def456"]
}
```

### フィールド定義

| フィールド | 型 | 説明 |
|---|---|---|
| `risk_score` | int 0–100 | operational triage score。確率ではない。運用上の優先順位を表す |
| `severity` | enum | 想定被害の大きさ（`low / medium / high / critical`）。`risk_score` とは必ずしも単調対応しない |
| `policy_classes` | array | 行為クラス・分類信頼度・severity |
| `anomaly_indicators` | array | 異常インジケータ・サブクラス・分類信頼度・severity |
| `evidence` | array of string | スコア根拠の自然言語説明 |
| `recommended_action` | enum | 下記参照 |
| `trace_refs` | array of string | OTel export が有効な場合に付与される **optional** field |

> `risk_score` は運用上の優先順位を表し、`severity` は想定被害の大きさを表す。両者は必ずしも単調対応しない（低確信度でも被害が大きい場合は severity が high になりうる）。

### recommended_action の定義

| アクション | 挙動 |
|---|---|
| `observe` | 記録のみ。実行は継続 |
| `warn` | 実行継続だがオーケストレーター / 運用者に通知 |
| `quarantine` | 対象メッセージ / ノードを隔離し、下流への伝播を一時停止 |
| `block` | 実行拒否。明示的なオーバーライドなしでは処理しない |

### recommended_action の決定規則

confidence < 0.5 の finding は action 判定から除外する（前段フィルタ）。残った findings に対して上から順に評価し、最初に一致した rule を採用する。

```
1. P0 クラスが一致 かつ severity=critical                          → block
2. P0 クラスが一致 かつ severity=high
   または parent_flagged_propagation が一致（confidence ≥ 0.5）    → quarantine
3. P0/P1 クラスが一致 かつ severity=high 未満                      → warn
4. 検知なし または全 finding が confidence < 0.5                   → observe
```

#### quarantine の MVP スコープ

- quarantine は **message / node 単位の一時停止**を指す。session 全体の停止はスコープ外
- タイムアウトは設けず、オーケストレーター側の明示的な解除操作で再開する
- 解除 API の詳細設計は ADR-002 参照

---

## 5. スコアリングエンジン（Layer 1）

### severity の出所と統合規則

- **各 matched rule は個別に severity を持つ**
- 重複集約後の finding severity は、当該 finding に属する rule の最大値とする
- Output Contract の全体 severity は、全 findings の severity の最大値を採用する
- 順序：`low < medium < high < critical`

### risk_score の算出方式

```python
findings = deduplicate_by_class(matched_rules)  # 同一クラスは1件に集約

base  = max(f.confidence * f.weight for f in findings)
bonus = min(0.2, 0.05 * (len(findings) - 1))
risk_score = min(100, round((base + bonus) * 100))
```

- 同一 policy class / indicator に属する重複ルールは1件に集約してから計算する
- `base` は最強シグナルを主軸とする
- `bonus` は複数の独立した検知による相乗効果（上限 +20 点）
- MVP では全ルールの初期 weight は均等（1.0）とし、後続バージョンで調整する

### ルール設定ファイル形式

ルールは外部 YAML で管理し、本体の変更なく追加・更新できること：

```yaml
- id: "rule:instruction_override:001"
  description: "Detects common override phrases in content payload"
  targets:
    - field: "content"
    - field: "tool_context.description_raw"
  pattern: "ignore (previous|prior|all) instructions"
  match_type: "regex_case_insensitive"
  policy_class: "instruction_override"
  confidence: 0.85
  severity: "high"
  weight: 1.0
```

---

## 6. One-hop Risk Inheritance Rule

MVP での簡易継承ルール。Layer 3（汎用 graph aggregation）の代替として最小限の継承判定を提供する。

### 動作

1. メッセージを評価する際、`parent_message_id` が存在する場合は親の評価結果を参照する
2. 親の `recommended_action` が `warn / quarantine / block` のいずれかである場合、`parent_flagged_propagation` を anomaly indicator として付与する
3. `parent_flagged_propagation` の confidence は **固定値 0.7** とする（ADR-002 参照）
4. 継承は **1 ホップのみ**。祖父メッセージ以上の伝播は MVP スコープ外

### 設定項目

```yaml
risk_inheritance:
  enabled: true
  parent_action_threshold: ["warn", "quarantine", "block"]
  propagated_confidence: 0.7
  max_hops: 1  # MVP 固定。将来拡張用
```

---

## 7. OTel Export

### 要件

- OTel Span への attribute 付与（既存 trace に security semantics を追加する形）
- OTel Event として評価結果を記録
- 既存の OTel exporter（OTLP/gRPC・OTLP/HTTP）にそのまま乗れること

### Span Attributes（追加分）

```
trust.risk_score              int
trust.severity                string
trust.recommended_action      string
trust.policy_classes          string (JSON array)
trust.anomaly_indicators      string (JSON array)
```

### Event 名

```
trust.evaluation.completed
```

Event attributes に output contract の全フィールドを含める。`trace_refs` はこの export 後に付与する。

---

## 8. CLI / JSONL

```bash
# 単一メッセージの評価
$ att evaluate --message message.json

# JSONL ストリームの評価
$ att evaluate --stream messages.jsonl

# レポート出力
$ att report --input evaluations.jsonl --format table
```

入力・出力ともに JSONL（1行1メッセージ）。バッチ処理・ストリーム処理の両方に対応すること。

---

## 9. デモシナリオ要件

**tool description poisoning → one-hop 継承 → quarantine**

1. 悪意ある `description_raw` を持つ MCP サーバーのモックを用意
2. Agent A が当該ツールを MCP 経由で呼び出す
3. `hidden_instruction_embedding` を検知 → `risk_score: 65` / `warn` を発行
4. Agent A から Agent B へメッセージ転送（`parent_message_id` で連結）
5. one-hop inheritance rule により `parent_flagged_propagation` を**付与**
6. `risk_score: 82` / `quarantine` 発動
7. OTel スパンに全証跡が記録されていることを確認

**起動要件：** Docker Compose で1コマンド起動できること

---

## 10. 非機能要件

| 項目 | 要件 |
|---|---|
| レイテンシ（SLO） | 単一メッセージ評価 50ms 以下（ローカル標準環境・99パーセンタイル・OTel export 除く） |
| レイテンシ（目標） | 純評価時間 10ms 以下（stretch goal） |
| 言語 | Python（初期実装）。インターフェース契約は language-agnostic に保つ |
| 依存 | コア評価エンジンは外部 LLM API に依存しない（Layer 1） |
| ライセンス | Apache 2.0（予定） |
| テスト | 各ルールに対応するテストケース（正例・負例）を必須とする |

---

## 11. Non-goals（MVP）

- prompt injection の完全防御保証
- Layer 2（LLM 意図分類）・Layer 3（汎用 multi-hop session aggregation）
- 送信元偽装検知（`declared_provenance_mismatch` 等）
- UI / ダッシュボード
- モデル内部の解釈可能性の提供
- エージェント能力の真正性証明
- 法的責任分界の自動化
- 単体でのゼロデイ攻撃防止

---

## 12. 開発マイルストーン（案）

| フェーズ | 内容 | 目安 |
|---|---|---|
| M0 | Schema・Taxonomy・Output Contract の確定（ADR-001〜003 の決定含む） | 1週間 |
| M1 | Layer 1 評価エンジン + one-hop inheritance + CLI + JSONL | 2週間 |
| M2 | OTel export 実装 | 1週間 |
| M3 | デモシナリオ + README + OSS 公開 | 1週間 |
| M4（以降） | Layer 2 実装・LangGraph 統合・Layer 3 | TBD |

---

## 13. 未解決事項（ADR 候補）

| No. | 論点 | 文書 |
|---|---|---|
| ADR-001 | `execution_phase` の管理方法（registry か自由文字列か） | 別ファイル |
| ADR-002 | `parent_flagged_propagation` の confidence 決定と quarantine 解除 API | 別ファイル |
| ADR-003 | `tool_metadata_drift` の比較スコープと `description_raw` の redaction ポリシー | 別ファイル |
| 未定 | ルール設定ファイルのスキーマバージョニング戦略 | TBD |
| 未定 | `content_hash` の対象範囲（全ペイロードか構造化部分のみか） | TBD |
