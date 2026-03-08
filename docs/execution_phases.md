# Execution Phases — Recommended Values Registry

> ADR-001 の成果物。`execution_phase` フィールドの推奨値コアセットを管理する。

## 概要

`execution_phase` は Message Envelope Schema の extensible string フィールドである。
固定 enum ではなく、以下の推奨値を参照点として提供する。

ルール YAML でフェーズ条件を使う場合は `execution_phase_match` フィールドで指定する（任意）。
省略した場合はフェーズに関係なく全メッセージに適用する。

## コアセット

| Value | Description |
|---|---|
| `planning` | Task decomposition and planning phase |
| `retrieval` | External information retrieval phase |
| `tool_selection` | Tool selection and argument determination phase |
| `tool_execution` | Tool execution phase |
| `synthesis` | Result integration and response generation phase |
| `unknown` | Unknown or unclassified |

## 使用例

### Message Envelope

```json
{
  "execution_phase": "tool_execution"
}
```

### Rule YAML

```yaml
- id: "rule:tool_misuse_attempt:001"
  execution_phase_match:
    - "tool_selection"
    - "tool_execution"
```

## カスタム値の追加

コアセット外の値を自由に使用できる。
フレームワーク固有のフェーズ名（例：`langraph_node_pre_hook`）もそのまま使用可能。

ただし、ルールの移植性を考慮し、可能な限りコアセットの値を使うことを推奨する。
