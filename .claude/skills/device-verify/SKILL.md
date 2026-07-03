---
name: device-verify
description: Preflight + runbook for verifying the mobile app on a device via Expo Go. Use BEFORE starting any on-device manual checklist, and FIRST THING whenever the user reports "the app doesn't load / sign-in doesn't work / stuck on splash" on a device — most such reports are environment drift, not code.
---

# Device verification (Expo Go)

## Preflight — run ALL of these before debugging anything

```bash
# 1. LAN IP drift (the #1 recurring false alarm — Wi-Fi changes move the Mac's IP)
ipconfig getifaddr en0
grep EXPO_PUBLIC_API_URL /Users/adamfeldman/parcel-tracker/parcel-track-mobile/.env.local
# These must match. If not: update .env.local, then FULLY restart expo
# (env files are read once at bundler startup — Fast Refresh will not pick it up).

# 2. Backend up and reachable
curl -fsS http://localhost:8000/health

# 3. Metro/Expo running, and port 8081 not stolen by a stale window
lsof -nP -iTCP:8081 -sTCP:LISTEN
```

## Diagnosis order when the app misbehaves on device

1. **Your own most recent structural change** — especially anything touching
   Expo Router route files. A deleted/renamed route file (e.g. a tab group's
   `index.tsx`) hangs the splash screen with no error. This exact failure was
   once misdiagnosed as a Metro cache problem for a full round-trip.
2. **Environment** (preflight above): stale LAN IP, dead backend, stale Metro.
3. Only then: actual app logic. Read the Metro console and device error text —
   don't guess.

Restart rules: `.env*` change → restart `expo start`. Route file
added/renamed/deleted → **full restart, not Fast Refresh** (the route tree is
built at startup). New native dependency → restart, and install via
`npx expo install`, never plain `npm install`.

## Data

Seed with `/seed-demo-data` before starting the checklist — never hand-written
SQL. Match the checklist's expected figures to what the seed actually created
(check its summary output) instead of assuming zeros.

## Proving "no request was sent" gates

Role/permission gates that should suppress a request are proven with
`docker logs parceltrack-api --since 2m | grep <path>` — absence of the request
in API logs is the evidence, not the UI alone.

## When a check needs the user

Screen-mirroring/computer-use of the phone is flaky (macOS notifications steal
focus; access requests time out). Prefer: give the user a short numbered
checklist of taps + expected results, and have them report back. Ask them to
enable Do Not Disturb on the Mac if mirroring is used.
