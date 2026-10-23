# Rules for Claude in this repo

- Never run git commit, git push, git tag, git rebase, git reset or any command that changes git history or the remote.
  Don't stage files. The owner (Maryam) reviews and commits everything herself.
- Never add "Co-Authored-By", "Generated with Claude Code" or any AI attribution to commit messages, files, PRs or
  release notes.
- When work is finished, show `git status` and suggest commit messages with their files.
- Never read, print or commit .env or API keys. Don't modify data/ or stores/.
