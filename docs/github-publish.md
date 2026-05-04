# Publish To GitHub

Recommended first repository name:

```text
pocket-codex
```

Before publishing:

1. Confirm `.env` does not exist in Git history.
2. Confirm `data/` and `*.sqlite3` are not tracked.
3. Edit `README.md` with your preferred project name and description.
4. Choose a license. This scaffold uses MIT.
5. Push the repository.

```powershell
git init
git add .
git commit -m "Initial Pocket Codex scaffold"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/pocket-codex.git
git push -u origin main
```

If you accidentally commit secrets, rotate the leaked key or token immediately. Removing
the file from the latest commit is not enough once it has been pushed.

