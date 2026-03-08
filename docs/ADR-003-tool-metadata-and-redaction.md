# ADR-003: tool_metadata_drift の比較スコープと description_raw の redaction ポリシー

| 項目 | 内容 |
|---|---|
| ステータス | 提案中 |
| 決定者 | TBD |
| 作成日 | 2025-01 |
| 関連 | MVP要件定義 v0.3 Section 2・Section 3 |

---

## 背景

### 論点1: tool_metadata_drift の比較スコープ

`tool_metadata_drift` は「以前観測した tool description hash と異なる場合に検知する」と定義しているが、「以前観測した」が何を指すか（比較の単位とスコープ）が未定。

- `tool_name` だけで比較するのか
- `sender + tool_name` の組み合わせで比較するのか
- session 内に限定するのか
- ローカル永続キャッシュ全体で比較するのか

これによって検出精度と実装コストが大きく変わる。

### 論点2: description_raw の redaction ポリシー

`description_raw` は hidden instruction 検出に必要なフィールドだが、tool description にはプロプライエタリな情報・個人情報が含まれる場合がある。

MVP でどこまで redaction を許容し、どこから検出精度が下がるかを明文化する必要がある。

---

## 論点1: tool_metadata_drift の比較スコープ

### 検討した選択肢

**案A: session 内での同一 tool_name の前回観測値と比較**

同一 session_id 内で、同じ `tool_name` のメッセージが複数来た場合に hash を比較する。

**メリット**
- session スコープなのでインメモリで完結し、永続化不要
- セッション中の動的な description 書き換えを検出できる
- 実装がシンプル

**デメリット**
- 新しい session では前回 session との差分が分からない
- session をまたいだ hash 変化（攻撃者が session をまたいで description を書き換える）を検出できない

---

**案B: ローカルファイルキャッシュに sender + tool_name でハッシュを永続化**

`{sender}:{tool_name}` をキーにして `description_hash` をローカルファイルに保存し、セッションをまたいで比較する。

**メリット**
- session をまたいだ description 変化を検出できる
- 攻撃者が session 単位で書き換えを行う場合にも対応できる

**デメリット**
- ファイルキャッシュの管理が必要（失効・削除ポリシーが必要）
- 分散環境では複数インスタンス間でキャッシュが共有されない
- 初回観測時は常に「変化なし」になる（初回の基準値確立に時間がかかる）

---

**案C: インメモリキャッシュに tool_name のみでハッシュを管理（プロセスライフタイム）**

案A と案B の中間。プロセス起動中のみキャッシュを保持し、`tool_name` だけをキーにする。

**メリット**
- 永続化不要でシンプル
- 同一プロセス内では session をまたいで比較できる

**デメリット**
- プロセス再起動でキャッシュが消える
- `tool_name` だけだと sender が異なるツールを同一視してしまう可能性がある

---

### 決定（論点1）

**MVP では案A（session 内の同一 tool_name）を採用する。**

ただし、sender をキーの一部に含めるよう修正する：

> `tool_metadata_drift` は、同一 session_id 内の同一 `{sender}:{tool_name}` の組み合わせにおける直近観測 `description_hash` と比較する。

#### 理由

- MVP で「動くものを出す」という目標に対して、インメモリ・セッションスコープが最も実装しやすい
- デモシナリオ（単一セッション内での tool poisoning）はこのスコープで十分再現できる
- session をまたいだ比較（案B）は Layer 3 以降で対応する

#### 初回観測の扱い

session 内で初めて観測した `{sender}:{tool_name}` の場合は、hash を記録するのみで `tool_metadata_drift` は発行しない。

#### 設定項目

```yaml
tool_metadata_tracking:
  scope: "session"  # "session" | "process" | "persistent" (将来対応)
  key_components: ["sender", "tool_name"]
```

---

## 論点2: description_raw の redaction ポリシー

### description_raw が必要な理由

`hidden_instruction_embedding` の検出には `tool_context.description_raw` の本文が必要。これがない場合：

- ツール説明文への hidden instruction 埋め込みが検出できない
- `tool_metadata_drift`（hash 差分）は検出できる（本文不要）が、「何が変わったか」は分からない

### redaction の選択肢

**案A: redaction 不可（本文必須）**

`description_raw` は必須フィールドとし、評価精度を最大化する。

**メリット**
- 最も高い検出精度

**デメリット**
- 機密性の高い tool description を外部ツールに渡すことへの抵抗がある
- エンタープライズ採用で障壁になる可能性がある

---

**案B: 完全 optional（本文なしでも動作）**

`description_raw` は optional とし、提供しない場合は `hidden_instruction_embedding` の検出範囲が縮小することをドキュメントで明示する。

**メリット**
- 採用障壁が低い
- プライバシー要件に柔軟に対応できる

**デメリット**
- 提供しない場合に最も重要な攻撃ベクタ（tool description poisoning）の一部が見えなくなる

---

**案C: 部分 redaction のサポート（プレースホルダー置換）**

`description_raw` の一部をプレースホルダーで redact した状態で渡すことを許容する。redact 済み部分のパターンマッチはスキップする。

```json
"description_raw": "このツールは[REDACTED]を処理します。ignore previous instructions"
```

**メリット**
- 機密部分のみ redact しつつ、非機密部分の検出は継続できる
- ユーザーが検出精度とプライバシーのトレードオフを制御できる

**デメリット**
- 実装がやや複雑
- redact の粒度によって検出効果が変わるため、ユーザーが判断を要する

---

### 決定（論点2）

**案B（完全 optional）を基本とし、案C（部分 redaction）を将来拡張として記載する。**

#### 実装方針

1. `description_raw` は **optional** フィールドとする
2. `description_raw` が null の場合、`hidden_instruction_embedding` の検出対象は `content` フィールドのみとなる
3. この制限を output contract の `evidence` に含める：

```json
"evidence": [
  "hidden_instruction_embedding: evaluated on content only (description_raw not provided)"
]
```

4. README と CLI のヘルプに以下を明示する：

> `description_raw` を提供しない場合、tool description 経由の hidden instruction（tool poisoning）は検出できません。
> 機密情報を含む場合は [REDACTED] プレースホルダーによる部分 redaction を検討してください（将来対応）。

#### セキュリティ上の注意

- `description_raw` はログやOTelスパンに平文で出力される可能性がある
- 機密情報を含む場合は OTel exporter の設定で該当フィールドをフィルタリングすること
- このガイダンスをドキュメントに追記する

---

## 影響範囲

- Message Envelope Schema：`content` フィールドを追加（論点1に関連）
- Schema：`tool_context.description_raw` は optional のまま
- 評価エンジン：session スコープの hash キャッシュを追加
- Output Contract：`evidence` に検出制限の注記を含める
- ドキュメント：redaction ガイダンスを追加
- 設定ファイル：`tool_metadata_tracking` セクションを追加
