---
name: ship-it
description: Definition-of-done checks plus the merge → sync → cleanup ritual for this repo. Use when a task is believed finished, when the user says "merge this / lets merge the branch / sync and clean up", or before reporting any implementation task as complete.
---

# Ship it

## 1. Definition of done — run the checks for whatever you touched

Backend (`parcel-track/`):
```bash
cd /Users/adamfeldman/parcel-tracker/parcel-track
uv run ruff format --check . && uv run ruff check . && uv run mypy app
```
Then **hand the test suite to the user**: "run `uv run pytest tests/ -q` in
your terminal and paste failures" — he runs long suites himself. Run only
quick targeted tests (`uv run pytest tests/unit/test_x.py -q`) yourself.

Mobile (`parcel-track-mobile/`):
```bash
cd /Users/adamfeldman/parcel-tracker/parcel-track-mobile
npx tsc --noEmit && npm test && npm run lint && npm run format:check
```
UI changes additionally need the on-device pass — use `/device-verify`.
A merge with formatter/lint failures has shipped before; these are blocking.

## 2. PR & CI

- Never commit to `main`. Feature branch → push → `gh pr create`.
- Wait for CI with the Monitor tool or a background
  `until gh pr checks <n> ...; do ...; done` loop — **never `sleep N &&`**.
- One red CI run on an unrelated job (e.g. a setup-step flake) → re-run that
  job once before digging.

## 3. Merge & sync

```bash
gh pr merge <n> --merge --delete-branch
git -C /Users/adamfeldman/parcel-tracker checkout main
git -C /Users/adamfeldman/parcel-tracker pull
git -C /Users/adamfeldman/parcel-tracker fetch --prune
```

## 4. Cleanup (the part that always gets forgotten)

```bash
git -C /Users/adamfeldman/parcel-tracker branch --merged main   # delete listed feature branches
git -C /Users/adamfeldman/parcel-tracker worktree list          # remove stale ones
git -C /Users/adamfeldman/parcel-tracker worktree prune
```
- A branch name "already used by worktree" error means a stale worktree is
  holding it — `git worktree remove <path>` first.
- Report (don't silently kill) long-running background processes: Metro,
  `docker compose`, watchers. Ask which to keep if unsure.
- Confirm `main` CI is green after merge before declaring victory.
