# リポジトリ準備（フォーク・リネーム・安全運用）

## 1) ローカルディレクトリ名の変更

```bash
mv /Users/tadayoshi_miura/workspace/rag-research-agent-template /Users/tadayoshi_miura/workspace/<NEW_REPO_NAME>
```

## 2) フォーク（Org）

Org配下にフォークを作成し、ローカルのリモートを更新します。

```bash
cd /Users/tadayoshi_miura/workspace/<NEW_REPO_NAME>
git remote set-url origin https://github.com/<ORG>/<NEW_REPO_NAME>.git
```

## 3) シークレット安全確認

```bash
# .env が追跡されていないことを確認
git ls-files .env

# ignore設定の確認
git status -s
```

## 4) .env運用

- `.env` はローカル専用
- `.env.example` が公開用テンプレ
