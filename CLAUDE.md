# CLAUDE.md — agent-trust-telemetry

## このファイルについて

Claude Code がこのリポジトリで作業を開始するための文脈・決定済み仕様・最初のタスクをまとめたファイル。
詳細仕様は `docs/` を参照すること。

---

## プロジェクトの一言説明

> prompt injection を遮断し切ることではなく、
> instruction contamination の発生・継承・累積を trace 上で観測可能にする
> エージェント間通信向け trust telemetry middleware

**中心命題："trusted sender であっても trusted content とは限らない"**

このプロジェクトは「防御製品」ではなく「信頼性計測インフラ」として設計する。
完全防御を約束しない代わりに、**何が起きているかを見えるようにすることを約束する**。

---

## 既存ツールとの関係（競合ではなく補完）

| ツール | 主眼 |
|---|---|
| Lakera Guard | 単発メッセージの point-in-time screening |
| LangSmith | observability・デバッグ・tracing |
| **本ツール** | security semantics over traces + inter-agent trust propagation |

独自監視基盤を要求せず、既存 OTel スタックに重ねて導入できる形を維持すること。

---

## 現在のフェーズ

**M0（実装開始直前）**

ADR-001〜003 が決定済み。MVP 要件定義 v0.3 が基準文書。
最初のタスクは下記「M0 でやること」を参照。

---

## 決定済み：固定インターフェース

**これらは MVP 以降も破壊的変更を避ける安定インターフェース。**
実装中に変更したい場合は必ず確認すること。

### Message Envelope Schema

```json
{
  "message_id":        "msg:uuid-v4",
  "parent_message_id": "msg:uuid-v4 | null",
  "timestamp":         "ISO8601",
  "sender":            "string",
  "receiver":          "string",
  "channel":           "mcp | a2a | internal | unknown",
  "role":              "tool_call | content | system | unknown",
  "execution_phase":   "string (extensible, see docs/execution_phases.md)",
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

### Output Contract

```json
{
  "schema_version": "0.1",
  "message_id":     "string",
  "trace_id":       "string",
  "session_id":     "string",
  "evaluated_at":   "ISO8601",
  "risk_score":     0,
  "severity":       "low | medium | high | critical",
  "policy_classes": [
    {"name": "string", "confidence": 0.0, "severity": "string"}
  ],
  "anomaly_indicators": [
    {"name": "string", "subclass": "string | null", "confidence": 0.0, "severity": "string"}
  ],
  "evidence":           ["string"],
  "recommended_action": "observe | warn | quarantine | block",
  "trace_refs":         ["string"]
}
```

- `risk_score`：operational triage score（0–100）。確率ではない
- `severity`：想定被害の大きさ。`risk_score` と必ずしも単調対応しない
- `trace_refs`：OTel export が有効な場合に付与される optional field

### Policy Violation Taxonomy

**Policy Violation Classes（行為クラス）**

| クラス | 優先度 |
|---|---|
| `instruction_override` | P0 |
| `privilege_escalation_attempt` | P0 |
| `secret_access_attempt` | P0 |
| `exfiltration_attempt` | P1 |
| `tool_misuse_attempt` | P1 |

**Anomaly Indicators（異常インジケータ）**

| インジケータ | 優先度 |
|---|---|
| `hidden_instruction_embedding` | P0 |
| `provenance_or_metadata_drift` | P1 |

**MVP で実装する provenance サブクラス（2つのみ）**

- `tool_metadata_drift`：同一 session 内の `{sender}:{tool_name}` の description_hash 変化
- `parent_flagged_propagation`：親メッセージが warn/quarantine/block の場合の one-hop 継承

### recommended_action 決定規則

```
前段フィルタ: confidence < 0.5 の finding は除外

1. P0 + severity=critical                                     → block
2. P0 + severity=high  OR  parent_flagged_propagation ≥ 0.5  → quarantine
3. P0/P1 + severity=high 未満                                 → warn
4. 検知なし OR 全 finding が confidence < 0.5                 → observe
```

### risk_score 算出

```python
findings = deduplicate_by_class(matched_rules)
base  = max(f.confidence * f.weight for f in findings)
bonus = min(0.2, 0.05 * (len(findings) - 1))
risk_score = min(100, round((base + bonus) * 100))
```

### One-hop Risk Inheritance

```yaml
risk_inheritance:
  enabled: true
  parent_action_threshold: ["warn", "quarantine", "block"]
  propagated_confidence: 0.7   # 固定値（ADR-002 で決定済み）
  max_hops: 1
```

---

## 決定済み：ADR サマリ

詳細は `docs/ADR-001〜003` を参照。

| ADR | 論点 | 決定 |
|---|---|---|
| ADR-001 | `execution_phase` の管理 | 推奨値レジストリ方式（extensible string + `docs/execution_phases.md`）。`execution_phase_group` は MVP 未実装 |
| ADR-002 | `parent_flagged_propagation` の confidence | 固定値 0.7。quarantine 解除は本番はツール外、デモ用に `att quarantine` CLI を別途提供 |
| ADR-003 | `tool_metadata_drift` の比較スコープ | session 内の `{sender}:{tool_name}` の直近 hash と比較。`description_raw` は optional、未提供時は `hidden_instruction_embedding` の tool 側検出が無効になり evidence に注記 |

---

## MVP スコープ

### In scope

- Message Envelope Schema の実装
- Policy Violation Taxonomy + Layer 1 検出ロジック（LLM不使用）
- One-hop risk inheritance rule
- Output Contract（JSON schema）
- OTel span/event export
- CLI：`att evaluate` / `att report` / `att quarantine`（デモ用）
- JSONL 入出力
- Docker Compose デモ（tool poisoning → one-hop 継承 → quarantine）

### Out of scope（MVP以降）

- Layer 2（LLM による意図分類）
- Layer 3（multi-hop graph / session risk aggregation）
- 送信元偽装検知（`declared_provenance_mismatch` 等）
- UI / ダッシュボード
- 署名付きエクスポート・監査台帳
- webhook / 外部通知
- マルチフレームワーク対応（LangGraph・CrewAI 等）

### Non-goals（原理的にやらない）

- prompt injection の完全防御保証
- モデル内部の解釈可能性の提供
- エージェント能力の真正性証明
- 法的責任分界の自動化
- 単体でのゼロデイ攻撃防止

---

## M0 でやること（最初のタスク）

以下の5ファイルを生成・確定することが M0 のゴール。

```
src/schemas/envelope.json          # Message Envelope の JSON Schema (Draft 2020-12)
src/schemas/output.json            # Output Contract の JSON Schema
rules/builtin/instruction_override.yaml
rules/builtin/hidden_instruction.yaml
tests/schemas/test_envelope.py     # 正例・負例のバリデーションテスト
```

**実装言語：Python**
**ライセンス：Apache 2.0**
**依存方針：コア評価エンジンは外部 LLM API に依存しない**

---

## 推奨ディレクトリ構成

```
agent-trust-telemetry/
├── CLAUDE.md
├── docs/
│   ├── concept-v4.md
│   ├── mvp-requirements-v0.3.md
│   ├── future-considerations.md    # MVP以降の拡張候補
│   ├── execution_phases.md
│   ├── ADR-001-execution-phase.md
│   ├── ADR-002-propagation-and-quarantine.md
│   └── ADR-003-tool-metadata-and-redaction.md
├── src/
│   ├── schemas/
│   │   ├── envelope.json
│   │   └── output.json
│   └── att/
│       ├── __init__.py
│       ├── evaluator.py
│       ├── taxonomy.py
│       ├── scorer.py
│       ├── inheritance.py
│       └── exporters/
│           └── otel.py
├── rules/
│   └── builtin/
│       ├── instruction_override.yaml
│       └── hidden_instruction.yaml
├── tests/
│   └── schemas/
│       └── test_envelope.py
├── demo/
│   └── docker-compose.yml
└── pyproject.toml
```

---

## 非機能要件

| 項目 | 要件 |
|---|---|
| レイテンシ（SLO） | 50ms 以下（ローカル標準環境・99p・OTel export 除く） |
| レイテンシ（目標） | 10ms 以下（stretch goal） |
| テスト | 各ルールに正例・負例テストケースを必須とする |

---

## 開発コマンド

```bash
# セットアップ
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,otel]"

# テスト
pytest                                    # 全テスト
pytest --cov=att --cov-report=term-missing  # カバレッジ付き
pytest tests/schemas/                     # スキーマテストのみ

# Lint & 型チェック
ruff check src/ tests/                    # リンター
ruff check --fix src/ tests/              # 自動修正
mypy src/                                 # 型チェック
```

---

## 開発規約

- **コミットメッセージ**：Conventional Commits 形式（英語）
  - 例：`feat(evaluator): add instruction_override detection`
- **コード内コメント**：英語
- **ドキュメント**：日本語可
- **テスト**：各ルールに正例・負例テストケースを必須とする
- **依存**：コア評価エンジンは外部 LLM API に依存しない
- **Python バージョン**：3.10+

---

## 参照ドキュメント

| ファイル | 内容 |
|---|---|
| `docs/mvp-requirements-v0.3.md` | MVP の詳細仕様（基準文書） |
| `docs/concept-v4.md` | プロジェクトの設計思想・背景 |
| `docs/future-considerations.md` | MVP 以降の拡張候補（Layer 2/3・商用化等） |
| `docs/ADR-001〜003` | 実装判断の記録 |
| `docs/execution_phases.md` | execution_phase 推奨値（ADR-001 の成果物） |
