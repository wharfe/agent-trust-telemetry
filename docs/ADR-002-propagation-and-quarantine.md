# ADR-002: parent_flagged_propagation の confidence 決定と quarantine 解除 API

| 項目 | 内容 |
|---|---|
| ステータス | 提案中 |
| 決定者 | TBD |
| 作成日 | 2025-01 |
| 関連 | MVP要件定義 v0.3 Section 4・Section 6 |

---

## 背景

### 論点1: parent_flagged_propagation の confidence 決定方法

one-hop risk inheritance rule では、親メッセージが flagged の場合に子メッセージへ `parent_flagged_propagation` を付与する。このとき付与する confidence をどう決めるかが未定。

候補は主に2つ：

1. **親の最大 confidence を継承し減衰させる**（例：親の最大 confidence × 0.7）
2. **固定値を使う**（例：confidence = 0.7 を常に付与）

### 論点2: quarantine 解除 API の設計

quarantine を発動した場合、オーケストレーター側が解除するためのインターフェースが必要。MVP では何を最小限として定義するかが未決。

---

## 論点1: confidence 決定方法

### 検討した選択肢

**案A: 親の最大 confidence を継承し減衰させる**

```python
parent_max_confidence = max(f.confidence for f in parent.findings)
propagated_confidence = parent_max_confidence * decay_factor  # default: 0.7
```

**メリット**
- 親の検知強度が子に反映される（強い検知は強く継承される）
- 直感的

**デメリット**
- 親の findings を参照する必要があり、評価エンジンに状態管理が必要
- decay_factor の根拠が薄く、チューニングが難しい
- 親の confidence の意味が policy class によって異なるため、混在すると解釈がぶれる

---

**案B: 固定値（recommended_action ベースの条件付き付与）**

親の `recommended_action` が `warn / quarantine / block` のいずれかの場合に `parent_flagged_propagation` を付与し、confidence は **固定値 0.7** とする。

```python
if parent.recommended_action in ("warn", "quarantine", "block"):
    add_indicator("parent_flagged_propagation", confidence=0.7)
```

**メリット**
- 実装がシンプル。親の findings の詳細を参照不要
- `recommended_action` は既に意味論が確定している値なので判定が安定する
- MVP の「動くものを出す」に集中できる

**デメリット**
- 親の検知強度が confidence に反映されない（warn でも quarantine でも同じ confidence になる）
- 精度的には案Aより粗い

---

### 決定（論点1）

**案B（固定値）を採用する。**

#### 理由

- MVP では評価エンジンを stateless に保つことを優先する。親の findings を参照するには評価セッションの状態管理が必要になり、実装コストが上がる
- `recommended_action` は既に複数の findings を統合した判断結果であり、これを閾値にすることは十分意味論的
- confidence の精緻化は Layer 3 で対応する

#### 実装詳細

```yaml
risk_inheritance:
  enabled: true
  parent_action_threshold: ["warn", "quarantine", "block"]
  propagated_confidence: 0.7
  max_hops: 1
```

confidence 0.7 の根拠：`recommended_action` ベースの条件付きなので「それなりに信頼できる継承シグナル」として設定。将来のチューニングに備えて設定値として外部化する。

---

## 論点2: quarantine 解除 API

### 要件の整理

MVP の quarantine は「message / node 単位の一時停止」であり、解除にはオーケストレーター側からの明示的な操作が必要。

本ツール（telemetry middleware）が quarantine の**実施**を担う範囲と、**解除の仕組み**を担う範囲を分ける必要がある。

### 検討した選択肢

**案A: 解除 API を本ツールが持つ**

本ツールが quarantine 状態を保持し、解除エンドポイントを提供する。

**メリット**
- 一元管理できる

**デメリット**
- 本ツールが stateful になる
- MVP の範囲を大幅に超える
- オーケストレーターとの結合が強くなる

---

**案B: 解除は本ツールのスコープ外とし、イベントで通知のみ行う**

本ツールは `recommended_action: quarantine` を output contract に含めて通知するだけ。実際に「止める」かどうか・「解除する」かどうかはオーケストレーター側の責任とする。

**メリット**
- 本ツールが stateless のまま保てる
- オーケストレーターの実装に依存しない
- MVP の輪郭を守れる

**デメリット**
- 「quarantine を実際に機能させる」ためにはオーケストレーター側の実装が必要
- デモで quarantine の効果を示すには、デモ用のオーケストレーターが必要

---

**案C: MVP 限定のシンプルな状態管理をローカルに持つ**

評価エンジンが軽量なインメモリの quarantine リストを持ち、CLI / JSONL 評価時に `quarantined` フラグを出力に付与する。解除は `att quarantine release --message-id msg:xxx` で行う。

**メリット**
- デモで quarantine の動作を示しやすい
- stateless を崩すが、MVP 限定の最小実装として許容範囲

**デメリット**
- 永続化なし（プロセス再起動で状態消失）
- 本番用途には使えない

---

### 決定（論点2）

**案B をベースとし、デモ用に案C の最小実装を別途提供する。**

#### 本番想定の設計（案B）

- 本ツールの output contract に `recommended_action: quarantine` を含める
- 実際の処理停止・解除はオーケストレーター側の責任
- ドキュメントに「quarantine を機能させるためのオーケストレーター側実装例」を記載する

#### デモ用実装（案C・MVP 限定）

```bash
# quarantine 発動済み message の確認
$ att quarantine list

# 解除
$ att quarantine release --message-id msg:xxx

# 全解除
$ att quarantine clear
```

- インメモリ管理のみ。永続化なし
- `README` にデモ用と明示し、本番用途でないことを注記する

---

## 影響範囲

- 評価エンジン：stateless 設計を維持（論点1）
- Output Contract：`recommended_action` フィールドは既存のまま
- CLI：デモ用に `att quarantine` サブコマンドを追加（MVP 限定）
- ドキュメント：オーケストレーター実装例を追加
