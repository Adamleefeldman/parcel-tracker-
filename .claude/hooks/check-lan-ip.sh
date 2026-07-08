#!/bin/bash
# SessionStart hook: warn when this Mac's LAN IP has drifted from the mobile
# app's .env.local. Stale IPs after a Wi-Fi change are the #1 cause of
# "Expo Go can't sign in / request timed out" false alarms.
ROOT="${CLAUDE_PROJECT_DIR:-/Users/adamfeldman/parcel-tracker}"
ENV_FILE="$ROOT/parcel-track-mobile/.env.local"
[ -f "$ENV_FILE" ] || exit 0

current=$(ipconfig getifaddr en0 2>/dev/null)
[ -n "$current" ] || exit 0

configured=$(sed -n 's|^EXPO_PUBLIC_API_URL=http://\([0-9.]*\).*|\1|p' "$ENV_FILE" | head -1)
[ -n "$configured" ] || exit 0

if [ "$configured" != "$current" ]; then
  msg="LAN IP drift: parcel-track-mobile/.env.local points at $configured but this Mac is now $current. Expo Go on a physical device cannot reach the backend until .env.local is updated AND expo is fully restarted (env files load once at bundler startup)."
  printf '{"systemMessage": "%s", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "%s"}}\n' "$msg" "$msg"
fi
exit 0
