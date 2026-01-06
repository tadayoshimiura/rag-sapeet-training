# Repo Setup (Fork + Rename + Safety)

## 1) Rename local directory

```bash
mv /Users/tadayoshi_miura/workspace/rag-research-agent-template /Users/tadayoshi_miura/workspace/<NEW_REPO_NAME>
```

## 2) Fork (Org)

Create a fork under your Org, then set the new remote:

```bash
cd /Users/tadayoshi_miura/workspace/<NEW_REPO_NAME>
git remote set-url origin https://github.com/<ORG>/<NEW_REPO_NAME>.git
```

## 3) Secret safety checks

```bash
# .env should NOT be tracked
git ls-files .env

# check ignored files
git status -s
```

## 4) .env usage

- `.env` is local only
- `.env.example` is the public template

