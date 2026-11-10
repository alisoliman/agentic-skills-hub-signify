---
name: ship-it
description: Ship the current change for review. Runs the tests, commits to a feature branch, pushes, opens or updates the pull request, and waits for its live Azure Static Web Apps preview URL. Use when the user says "ship it", "open a PR", "deploy a preview", or "make it live for review". Never merges, never pushes to main, never force-pushes.
license: MIT
---

# Ship it

Turn the work in this repository into a pull request with a live preview that people can open on their own devices. A bundled script does the mechanics, so every run follows the same safe steps and ends with the same two lines: `PR_URL=` and `PREVIEW_URL=`.

## 1. Check what will ship

1. Run `git status` and look at the diff. Only the intended changes should ship. Generated files such as `site/hub.json` are ignored on purpose; never force-add them.
2. If unrelated files changed, ship only the intended ones with `--paths <file> <file> ...`.
3. Write a commit message: an imperative subject under 72 characters (for example `Add skill detail pages`), optionally followed by a blank line and a short body that explains why.

## 2. Run the script

From the repository root:

```bash
python3 .github/skills/ship-it/scripts/ship.py --message "Add skill detail pages"
```

On Windows use `py -3` (or `python`) instead of `python3`. If this skill is installed somewhere else, run the `scripts/ship.py` that sits next to this file.

| Option | Use it to |
| --- | --- |
| `--message "..."` | commit message for uncommitted changes (required when there are any) |
| `--title "..."` / `--body "..."` | set the pull request title and description (defaults: first commit subject and a list of commits) |
| `--paths a b` | commit only these paths |
| `--branch feat/name` | choose the branch name when starting from the default branch (default: `feat/<slug>`) |
| `--draft` | open the pull request as a draft |
| `--timeout 600` | wait longer for the preview (default: 300 seconds) |
| `--no-wait` | open or update the pull request without waiting for the preview |
| `--dry-run` | print the plan without changing anything |

The script, in order:

1. runs `npm test` and stops if it fails: nothing is committed or pushed;
2. moves the work to a feature branch: it creates `feat/<slug>` when you are on the default branch and keeps your changes;
3. commits the intended changes with your message;
4. pushes the branch, never with force and never to the default branch;
5. opens the pull request, or updates the one that already exists for this branch;
6. waits for the deploy workflow's preview and checks that `<preview>/hub.json` reports the pushed commit, so the URL it prints shows exactly this change.

## 3. Report back

Give the user the pull request URL and the preview URL from the final `PR_URL=` and `PREVIEW_URL=` lines, and say in one sentence what the preview shows. Shipping the next change to the same pull request is the same command run again from the same branch.

## When it stops

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 1 | Tests failed | Fix the failures, then run the same command again. |
| 2 | Refused, or a git/GitHub error | Read the message: sign in with `gh auth login`, resolve the push rejection by pulling or rebasing, or leave the default branch. |
| 3 | Preview not verified in time | The workflow may need approval, still be running, or lack the `AZURE_STATIC_WEB_APPS_API_TOKEN` secret. The message links the run. Running the same command again keeps waiting without creating duplicate commits or pull requests. |

## Rules

- Never merge the pull request: a person reviews and merges it.
- Never push to `main` or the default branch, never force-push, and never rewrite published history.
- Never print, commit or paste secrets or tokens.
