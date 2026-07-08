# CLAUDE.md — parcel-tracker (monorepo root)

This repo holds two subprojects. Each has its own detailed doc — **read the one
for the code you're touching before changing anything**:

| Path | What | Doc |
|---|---|---|
| `parcel-track/` | FastAPI backend (Python 3.12, uv, Postgres, Celery) | [`parcel-track/CLAUDE.md`](parcel-track/CLAUDE.md) |
| `parcel-track-mobile/` | Expo (React Native) mobile client | [`parcel-track-mobile/AGENTS.md`](parcel-track-mobile/AGENTS.md) |

## Working directory rules

- Sessions often start HERE at the repo root. Backend commands must run from
  `parcel-track/`, mobile commands from `parcel-track-mobile/`. Shell state does
  not persist between Bash calls, so **use absolute paths or prefix every
  command** (`cd /Users/adamfeldman/parcel-tracker/parcel-track && ...`).
  Wrong-cwd failures (`cd: no such file or directory: parcel-track`,
  `app/... not found`) are a recurring time sink — check where you are first.
- Doubled paths (`parcel-track-mobile/parcel-track-mobile/...`) mean you were
  already inside the subdir.

## Communication style

- **Plain language first.** The user is technical but not steeped in
  backend/git jargon. Lead with what a thing means in plain English, then the
  technical term in parentheses — e.g. "the branch has uncommitted work on it
  (a 'dirty' branch)". Never hand back an unexplained term like "dirty",
  "rebase", "idempotent", or "single-flight".
- When proposing anything with a per-use or subscription cost (APIs, hosted
  services), present price alongside quality before implementing.

## Tests, CI, and waiting

- **The user runs long test suites himself** in his VSCode terminal. Run quick,
  targeted tests to check your own work; for the full backend suite, hand off:
  "run `uv run pytest tests/ -q` when ready" and wait for his result.
- **Never poll with `sleep N && <check>`** — it gets blocked. To wait on CI or
  another external process, use the Monitor tool / a background `until` loop,
  or just hand off and pick up next turn.
- Before reporting ANY task as done: backend → `uv run ruff format --check .`
  and `uv run ruff check .` must pass; mobile → `npx tsc --noEmit`,
  `npm run lint`, `npm run format:check`. "Tests pass" is not done if the
  formatter fails — this has burned us before.

## Git workflow

- `main` is protected in spirit: **never commit or push to it directly.** One
  feature branch + PR per task, branched from a fresh `origin/main`.
- Merge only after CI is green. After merging: sync local `main`, delete the
  local + remote feature branch, and remove any stale worktrees
  (`git worktree prune` + check `.claude/worktrees/`). Use the `/ship-it`
  skill for this whole ritual.
- Destructive git (`reset --hard`, `push --force`, `clean`) needs explicit
  user direction naming the target — prefer `git reset --keep`.

## Secrets

- Real credentials live in `parcel-track/secrets/` (mounted as Docker secrets
  at `/run/secrets/` in containers). **Never `cat` these files or print their
  values into the conversation** — reference them by path, load them into a
  command's environment without echoing.
- `.env` files are non-secret config only. Remember the two-database split:
  host `.env` targets local Docker Postgres; anything against prod Supabase
  requires `uv run --env-file .env.supabase ...` (see backend CLAUDE.md).

## Project skills (in `.claude/skills/`)

- `/seed-demo-data` — seed the local DB for manual verification. **Never
  hand-write seeding SQL**; the raw-SQL path has failed on enum labels, uuid
  casts, and junction-table defaults many times.
- `/device-verify` — preflight + runbook for Expo Go on-device checks. Run the
  preflight BEFORE debugging any "app broken on device" report.
- `/ship-it` — definition-of-done checks + merge/sync/cleanup ritual.
