#!/bin/bash
# Stop hook: when backend .py files have uncommitted changes, run ruff on just
# those files and surface failures. Catches "done but unformatted" before the
# user has to paste the failures back (this shipped broken more than once).
ROOT="${CLAUDE_PROJECT_DIR:-/Users/adamfeldman/parcel-tracker}"
cd "$ROOT" 2>/dev/null || exit 0

files=$(git diff --name-only HEAD -- 'parcel-track/*.py' 'parcel-track/**/*.py' 2>/dev/null | head -100)
[ -z "$files" ] && exit 0

cd parcel-track 2>/dev/null || exit 0
[ -d .venv ] || exit 0
rel=$(echo "$files" | sed 's|^parcel-track/||' | while read -r f; do [ -f "$f" ] && echo "$f"; done)
[ -z "$rel" ] && exit 0

# shellcheck disable=SC2086
fmt_out=$(uv run ruff format --check $rel 2>&1); fmt_rc=$?
# shellcheck disable=SC2086
lint_out=$(uv run ruff check --quiet $rel 2>&1); lint_rc=$?

if [ $fmt_rc -ne 0 ] || [ $lint_rc -ne 0 ]; then
  n_fmt=$(echo "$fmt_out" | grep -c 'Would reformat')
  n_lint=$(echo "$lint_out" | grep -Ec '^[^ ]+:[0-9]+:[0-9]+:')
  msg="ruff is unhappy with the modified backend files: $n_fmt unformatted, $n_lint lint finding(s). Fix before calling this done: cd parcel-track && uv run ruff format . && uv run ruff check ."
  printf '{"systemMessage": "%s"}\n' "$msg"
fi
exit 0
