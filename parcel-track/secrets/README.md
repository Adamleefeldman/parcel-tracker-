# `secrets/` — file-backed Docker secrets for the local dev stack

Each file in this directory is mounted read-only into the api / worker / beat
containers at `/run/secrets/<filename>`. Pydantic-Settings reads them
automatically because `Settings.Config.secrets_dir = "/run/secrets"` and the
filename must match the Settings field name (case-sensitive).

## Rules

- **Filename = Settings field name**, all caps. Example:
  `STORAGE_SECRET_ACCESS_KEY`. No `.txt` suffix, no quotes, no leading
  whitespace.
- **One value per file**, raw, no `KEY=` prefix. Trailing newlines are
  stripped by Pydantic.
- **Never commit value files.** `.gitignore` keeps everything except
  `.gitkeep` and this `README.md`. Verify with `git status` before pushing.
- **Never bake into the image.** `.dockerignore` excludes the directory.
  Compose mounts at runtime only.

## Required files (for `docker compose up` to succeed)

| File | Source |
|---|---|
| `STORAGE_ACCESS_KEY_ID` | Cloudflare R2 → Manage R2 API Tokens → Access Key ID |
| `STORAGE_SECRET_ACCESS_KEY` | Same token's Secret Access Key |

If either file is missing or empty, `docker compose up` fails fast with a
clear error from compose ("file not found") or, post-mount, from
Pydantic at boot (required field not provided). Both are intentional — the
stack should refuse to start without credentials.

## Adding a new secret

1. Add the field to `Settings` in `app/core/config.py`.
2. Add a top-level entry under `secrets:` in `docker-compose.yml` referencing
   `./secrets/<NEW_NAME>`.
3. Append `- source: <new_name>` / `target: <NEW_NAME>` to the
   `x-app-secrets:` anchor at the top of the compose file. All three
   services pick it up automatically.
4. Create `secrets/<NEW_NAME>` on disk with the raw value.

## Production note

In the deploy environment (Fly.io / Railway / k8s) you don't use this
directory. Each platform mounts secrets at `/run/secrets/<NAME>` (or
equivalent) from its own secret manager. The Settings class doesn't care
where the file came from — only that it exists at that path.
