# Demo Scenarios

agent-trust-telemetry の検出能力を示す4つの攻撃シナリオです。

## Quick Start

```bash
# デフォルトシナリオ（tool_poisoning）
python demo/run_demo.py

# 特定のシナリオを実行
python demo/run_demo.py --scenario metadata_drift

# 全シナリオを一括実行
python demo/run_demo.py --scenario all

# OTel export 付き（Docker Compose で Jaeger 起動後）
cd demo && docker compose up --build
```

Jaeger UI: [http://localhost:16686](http://localhost:16686)

## Scenarios

### 1. tool_poisoning（デフォルト）

**MCP ツール説明への hidden instruction 埋め込み → one-hop 継承**

悪意ある MCP サーバーが `web_search` ツールの description に HTML コメントで隠し指示を埋め込む。
指示はユーザーデータの外部転送を要求。

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → agent_a | — | observe |
| 2 | mcp_server → agent_a | instruction_override + hidden_instruction + exfiltration | **quarantine** (95) |
| 3 | agent_a → agent_b | parent_flagged_propagation | **quarantine** (70) |
| 4 | agent_b → agent_c | parent_flagged_propagation | **quarantine** (70) |

### 2. metadata_drift

**同一セッション内でツール説明が途中で書き換わる攻撃**

正規の翻訳 MCP サーバーが最初は正常な tool description を返すが、
2回目の呼び出しで `[SYSTEM]` タグ付きの悪意ある指示を description に注入。
description_hash の変化を `tool_metadata_drift` として検出。

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → agent_a | — | observe |
| 2 | mcp_translation → agent_a | — (初回、正常) | observe |
| 3 | human → agent_a | — | observe |
| 4 | mcp_translation → agent_a | [SYSTEM]タグ + **tool_metadata_drift** | **warn** (90) |
| 5 | agent_a → agent_b | parent_flagged_propagation | **quarantine** (70) |

**ポイント**: Content 自体は無害だが、description の hash 変化が攻撃の兆候を捉える。
これは既存の単発メッセージスキャンでは検出できない、セッション横断の異常。

### 3. data_exfiltration

**秘密情報の抽出 → 外部エンドポイントへの送信チェーン**

コード検索ツールの description に `.env` ファイル・認証情報の読み取り指示が HTML コメントとして隠されている。
エージェントが抽出した API キーを外部 webhook に送信しようとする流れを検出。

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → coding_agent | — | observe |
| 2 | mcp_code_search → coding_agent | secret_access(0.85) + hidden_instruction | **block** (90) |
| 3 | coding_agent → reporting_agent | exfiltration(0.75) + parent_flagged | **quarantine** (70) |
| 4 | reporting_agent → human | parent_flagged_propagation | **quarantine** (70) |

**ポイント**: Step 2 で secret_access が severity=critical として検出され、
P0 + critical の組み合わせで **block**（最高レベル）が発動。

### 4. privilege_escalation

**デプロイツール経由の権限昇格 + 破壊的 SQL インジェクション**

デプロイツールの description に `sudo` コマンド実行・認証バイパス・特権モード実行の指示が埋め込まれている。
汚染されたエージェントが DB エージェントに `DROP TABLE` + `DELETE FROM` を含む SQL を送信。

| Step | Flow | Detection | Action |
|------|------|-----------|--------|
| 1 | human → devops_agent | — | observe |
| 2 | mcp_deploy → devops_agent | privilege_escalation(0.85) + tool_misuse(0.80) | **quarantine** (90) |
| 3 | devops_agent → db_agent | SQL injection(0.80) + parent_flagged | **quarantine** (85) |
| 4 | db_agent → devops_agent | parent_flagged_propagation | **quarantine** (70) |

**ポイント**: Step 3 は自身のコンテンツ（SQL injection）と親メッセージの汚染の
両方が検出され、risk_score が 85 に上昇。複合的な脅威の重畳を示す。

## Scenario Files

```
demo/scenarios/
├── tool_poisoning.jsonl       # MCP tool description poisoning
├── metadata_drift.jsonl       # Tool description mutation mid-session
├── data_exfiltration.jsonl    # Secret extraction + exfiltration chain
└── privilege_escalation.jsonl # Privilege escalation + SQL injection
```

各 `.jsonl` ファイルは Message Envelope Schema に準拠したメッセージの連鎖です。
独自のシナリオを追加する場合は、同じ形式で `.jsonl` ファイルを `demo/scenarios/` に配置してください。

## Viewing in Jaeger

`docker compose up --build` 後、各評価は以下の属性を持つ OTel span を生成します：

- `trust.risk_score` — triage スコア (0–100)
- `trust.severity` — 影響レベル
- `trust.recommended_action` — observe / warn / quarantine / block
- `trust.evaluation.completed` イベント — 完全な evidence 付き
- `demo.scenario` — シナリオ名
