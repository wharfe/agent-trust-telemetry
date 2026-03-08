# ADR-001: execution_phase の管理方法

| 項目 | 内容 |
|---|---|
| ステータス | 提案中 |
| 決定者 | TBD |
| 作成日 | 2025-01 |
| 関連 | MVP要件定義 v0.3 Section 2 |

---

## 背景

Message Envelope Schema の `execution_phase` は、エージェントがメッセージを処理しているフェーズを表す。このフィールドがあることで、同じ文字列でも `tool_selection` フェーズと `synthesis` フェーズでは意味が異なるという**役割の文脈依存性**を捉えられる。

MVP要件では「extensible string とする。固定 enum にしない」としているが、管理方法を決めないと以下の問題が起きる：

- 実装者がそれぞれ別の文字列を使い始め、ルール YAML が特定実装に依存する
- Layer 2 / Layer 3 で phase ごとのリスク重み付けをしたい場合に、値の正規化コストが大きくなる
- OSS コントリビューターがルールを書く際の参照点がない

---

## 検討した選択肢

### 案A: 自由文字列（管理なし）

Envelope の `execution_phase` は完全に自由入力とし、ドキュメントに例示するだけ。

**メリット**
- 実装が最もシンプル
- フレームワーク固有の phase 名をそのまま使える

**デメリット**
- ルールが特定の文字列に依存し、移植性が低くなる
- 後で正規化が必要になった場合にコストが高い

---

### 案B: 推奨値レジストリ（ドキュメント管理）

コアセットを WELL_KNOWN_PHASES として docs / README に列挙し、任意の追加は自由とする。

```
planning
retrieval
tool_selection
tool_execution
synthesis
unknown
```

ルールは `execution_phase` を直接参照するのではなく、`execution_phase_group` という正規化済みグループで参照できるようにする（オプション）。

**メリット**
- コアセットが揃うことでルールの移植性が上がる
- 追加は自由なので実装を縛らない
- 将来の Layer 2 で phase ごとのリスク重み付けがしやすい

**デメリット**
- ドキュメントの維持が必要
- コアセット外の値をルールで扱う場合に少し複雑になる

---

### 案C: 固定 enum（バージョン管理）

`execution_phase` を schema バージョンで固定 enum にする。新しい値は schema バージョンアップで追加する。

**メリット**
- バリデーションが厳密にできる
- ツール間の互換性が高い

**デメリット**
- MVP には重すぎる
- フレームワーク固有の phase を表現できない
- schema の変更コストが高い

---

## 決定

**案B（推奨値レジストリ）を採用する。**

### 理由

- MVP の軽さを保ちつつ、ルールの移植性を確保できる
- 将来 Layer 2 / Layer 3 に進む際に phase ベースのリスク調整がしやすい
- コントリビューターへの参照点になる

### 実装方針

1. `execution_phase` は schema 上 `string` とする（バリデーションなし）
2. 推奨値コアセットを `docs/execution_phases.md` で管理する
3. ルール YAML でフェーズ条件を使う場合は `execution_phase_match` フィールドで指定する（任意）：

```yaml
- id: "rule:tool_misuse_attempt:001"
  ...
  execution_phase_match:
    - "tool_selection"
    - "tool_execution"
```

4. `execution_phase_match` を省略した場合はフェーズに関係なく全メッセージに適用する

### 推奨値コアセット（初期）

| 値 | 説明 |
|---|---|
| `planning` | タスク分解・計画立案フェーズ |
| `retrieval` | 外部情報の取得フェーズ |
| `tool_selection` | ツールの選択・引数決定フェーズ |
| `tool_execution` | ツールの実行フェーズ |
| `synthesis` | 結果の統合・回答生成フェーズ |
| `unknown` | 不明・未分類 |

---

## 影響範囲

- Message Envelope Schema：変更なし（`string` のまま）
- ルール YAML：`execution_phase_match` フィールドを任意追加
- ドキュメント：`docs/execution_phases.md` を新規作成
- バリデーション：MVP では phase 値の検証は行わない
