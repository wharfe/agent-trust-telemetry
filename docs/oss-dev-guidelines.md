# agentbond OSS開発ガイドライン

Claude Codeでの実装時に参照する、ディレクトリ構造・ドキュメント・CI/CDの規約まとめ。

---

## ディレクトリ構造

```
agentbond/
├── packages/
│   ├── core/
│   │   ├── src/
│   │   ├── package.json      ← "name": "@agentbond/core"
│   │   ├── tsconfig.json
│   │   └── README.md         ← パッケージごとに必ず置く
│   └── auth/
├── mcp-server/
├── docs/
│   ├── authorization.spec.md
│   └── llms.txt              ← エージェント向け発見可能性ファイル
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   └── release.yml
│   └── ISSUE_TEMPLATE/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                   ← 拡張子なし、MIT本文そのまま
└── README.md
```

**注意:** `packages/*/README.md` はnpmに公開したときそのパッケージのランディングページになる。省略しない。

---

## バージョニング戦略

- `0.1.0` = MVPリリース
- `1.0.0` = 外部採用に耐える安定版（破壊的変更ゼロポリシーの適用開始）
- `CHANGELOG.md` は [Keep a Changelog](https://keepachangelog.com) 形式を使う
- `Unreleased` セクションを常に先頭に置く

---

## コミットメッセージ規約（Conventional Commits）

```
feat(auth): add token revocation endpoint
fix(core): correct ISO datetime validation
docs: update llms.txt with new tool descriptions
chore: update dependencies
```

**なぜ最初から使うか:**
- `CHANGELOG.md` の自動生成が使えるようになる
- セマンティックバージョニングの自動判定が使えるようになる
- 途中から導入すると履歴が汚れる

---

## リリース管理: changesets

モノレポのリリース管理は `changesets` を使う（`release-please` より推奨）。

理由: パッケージ間に依存関係があるため、`@agentbond/auth` を更新する際に `@agentbond/core` のバージョンをどう扱うかをツールが補助してくれる。

---

## README.md の構成

```markdown
# agentbond

1行のキャッチコピー（何をするものか）

## Why

なぜ作ったか・何が問題か（思想）

## Quick Start

インストールと最小動作例（コピペで動く）

## Packages

| パッケージ | 役割 |
|---|---|
| @agentbond/core | 型定義 |
| @agentbond/auth | 認可エンジン |

## Design Principles

設計憲法（HANDOFFにある5原則）

## Status

現在のフェーズ・安定性の宣言

## Contributing / License
```

**Why を先に書く理由:** OSSで採用されるかどうかは「何ができるか」より「なぜ作ったか」で判断されることが多い。思想が明確なプロジェクトはここを最初から書く。

---

## llms.txt（エージェント向け発見可能性ファイル）

`docs/llms.txt` またはルートの `/llms.txt` に置く。
設計憲法の「発見可能性」原則に対応するファイル。

```
# agentbond

AIエージェントの認可・意図証明・契約を管理するガバナンスインフラ。

## @agentbond/auth

issueToken(params) - トークン発行
evaluateAction(action, tokenId) - 認可判定
revokeToken(tokenId) - トークン失効

## Endpoints
...
```

MCPエコシステムを前提にしたプロジェクトとして、最初から置いておく。

---

## package.json の必須フィールド

```json
{
  "name": "@agentbond/auth",
  "version": "0.1.0",
  "license": "MIT",
  "type": "module",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "files": ["dist", "README.md"],
  "repository": {
    "type": "git",
    "url": "https://github.com/yourname/agentbond"
  },
  "homepage": "https://github.com/yourname/agentbond/tree/main/packages/auth"
}
```

**`files` フィールドは必ず設定する。** `dist` と `README.md` のみ公開。`src` をうっかり公開しないように。

---

## CI（最低限の構成）

```yaml
# .github/workflows/ci.yml
- tsc --noEmit        # 型チェック
- eslint              # Lint
- vitest              # テスト
- publint             # npmパッケージ構造チェック
```

**`publint` について:** `exports` フィールドの設定ミスや型定義の漏れを検出する。npmに公開してから気づくとバージョンを汚すため、CIに最初から組み込む。

---

## CLAUDE.md（Claude Code用コンテキストファイル）

リポジトリルートに置くと、Claude Codeがプロジェクト固有のコンテキストを自動で読み込む。

```markdown
# CLAUDE.md

## このリポジトリについて
agentbondはAIエージェントの認可・ガバナンスインフラ。
パッケージスコープ: @agentbond/*
モノレポツール: pnpm workspaces + turborepo

## 実装ルール
- 型定義のみのファイルに実装ロジックを書かない
- 仕様書にないフィールドを善意で追加しない
- 不明点は実装を止めて質問する
- コミットはConventional Commits形式で書く

## 参照すべきドキュメント
- HANDOFF.md: アーキテクチャと設計憲法（必読）
- docs/authorization.spec.md: 認可判定の仕様（必読）
- oss-dev-guidelines.md: このファイル

## コマンド
- pnpm build: 全パッケージビルド
- pnpm test: 全テスト実行
- pnpm typecheck: 型チェック
- pnpm changeset: リリースノート追加
```

---

## 最初はやらなくていいこと

- VitePressなどのドキュメントサイト → パッケージが安定してから
- npm organizationの作成 → 公開直前でよい
- Codecovなどのカバレッジバッジ → 見栄えより中身を先に

---

## 最初から入れる3つ（優先順位）

1. **CI**（tsc + eslint + vitest + publint）
2. **CHANGELOG.md**（Keep a Changelog形式、Unreleased先頭）
3. **CLAUDE.md**（プロジェクト固有コンテキスト）

この3つだけ最初から入れれば、あとは作りながら追加できる。
