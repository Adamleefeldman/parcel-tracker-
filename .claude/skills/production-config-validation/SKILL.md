---
name: production-config-validation
description: Use whenever the user is setting up, auditing, or modifying application configuration — pydantic-settings / Settings class, environment variables, `.env` files, secrets management, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, CORS allowlist, allowed hosts, Docker secrets, production deployment config. Triggers on phrases like "set up config", "env vars", "Settings class", "pydantic-settings", "fail fast on misconfig", "production should reject X", "secrets management", "Docker secrets", "weak SECRET_KEY", "I shipped with the default password by mistake", or "the app booted with a placeholder key". Also use when reviewing a PR that adds a new setting — every new field should pass through the same validator.
---

# Boot-time config validation that refuses to start when misconfigured

A surprising number of production incidents trace back to **the app booted with a config it shouldn't have**: a placeholder `SECRET_KEY`, an `http://` storage endpoint, an empty `ALLOWED_HOSTS`, a `DATABASE_URL` pointing at localhost in prod. The defense is the same in every case: a `model_validator(mode="after")` on the `Settings` class that refuses to construct when production-only invariants don't hold. The app crashes before it serves a single request — loud, immediate, and visible in the deploy logs.

This skill is for FastAPI / Python services using `pydantic-settings`. The principle (fail fast, in code, with a useful error message) generalizes to any language.

## The shape

A `Settings(BaseSettings)` class with:

1. **Fields with sensible non-secret defaults** (development-friendly).
2. **A `_validate_settings(self) -> Self` model validator** that runs *after* field-level validation and enforces production-only rules.
3. **A blocklist of obvious placeholder secrets** (`changeme`, `secret`, `dev`, `default`, `password`, `test`).
4. **A `secrets_dir` for credential-class fields** (Docker / Kubernetes secrets mounted as files).
5. **An `is_production` property** for the validator to branch on, plus runtime use elsewhere.

The whole point is that *every* environment runs the validator at boot. Dev catches mistakes early; staging catches them again with prod-like rules; production refuses to start when the rules aren't met. There's no "skip validation in CI" escape hatch — if CI fails the validator, that's the message you wanted.

## Canonical template

```python
# app/core/config.py

from functools import lru_cache
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings

_PLACEHOLDER_SECRETS = frozenset({
    "changeme", "secret", "dev", "default", "password", "test",
})
_MIN_SECRET_KEY_LENGTH = 32  # 256 bits


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_NAME: str = "myapp"
    SECRET_KEY: str

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str         # async runtime — postgresql+asyncpg://...
    DATABASE_URL_SYNC: str    # alembic migrations  — postgresql://...

    # ── Auth ───────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    BCRYPT_ROUNDS: int = 12

    # ── Storage (S3/R2/etc.) ───────────────────────────────────────────────
    # Credentials are empty by default so host-side tests boot without a
    # /run/secrets mount; the production validator below requires non-empty.
    STORAGE_BUCKET: str
    STORAGE_ENDPOINT_URL: str
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Network ────────────────────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS: str = ""  # comma-separated
    ALLOWED_HOSTS: str = ""         # comma-separated
    TRUSTED_PROXIES: str = ""       # comma-separated

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @model_validator(mode="after")
    def _validate_settings(self) -> "Settings":
        # ── SECRET_KEY (every env) ─────────────────────────────────────────
        key = self.SECRET_KEY
        if len(key) < _MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters "
                f"(got {len(key)}). Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if key.lower().strip() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                f"SECRET_KEY looks like a placeholder ({key!r}). Set a real value."
            )

        # ── Production-only checks ─────────────────────────────────────────
        if self.is_production:
            if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
                raise ValueError(
                    "DATABASE_URL must use the 'postgresql+asyncpg://' scheme in production."
                )
            if not self.REDIS_URL or self.REDIS_URL == "redis://localhost:6379/0":
                raise ValueError(
                    "REDIS_URL must be set to a non-localhost Redis instance in production."
                )
            if not self.STORAGE_ENDPOINT_URL.startswith("https://"):
                raise ValueError("STORAGE_ENDPOINT_URL must use HTTPS in production.")
            if not self.STORAGE_ACCESS_KEY_ID:
                raise ValueError(
                    "STORAGE_ACCESS_KEY_ID must be set in production. "
                    "Mount via secret at /run/secrets/STORAGE_ACCESS_KEY_ID."
                )
            if not self.STORAGE_SECRET_ACCESS_KEY:
                raise ValueError(
                    "STORAGE_SECRET_ACCESS_KEY must be set in production."
                )
            if not self.cors_origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must be set in production. "
                    "Comma-separated list, e.g. 'https://app.example.com'."
                )
            if not self.allowed_hosts:
                raise ValueError(
                    "ALLOWED_HOSTS must be set in production. "
                    "Comma-separated list of Host header values."
                )

        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        # Pydantic-Settings reads files at this path named after each field
        # (e.g. /run/secrets/STORAGE_SECRET_ACCESS_KEY) when no env var is
        # set. Lookup order: env var → secrets file → field default. Docker
        # Compose mounts secrets here; managed platforms can do the same.
        secrets_dir = "/run/secrets"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

## Design rules — and why they matter

### Rule 1: Validate in a `model_validator(mode="after")`, not field validators

`mode="after"` runs after all fields are populated, so the validator can branch on `APP_ENV` to decide which rules to enforce. Field-level validators don't see siblings. Use field validators only for field-shape rules (string format, range), not for cross-field invariants.

### Rule 2: Fail fast — `raise ValueError`, don't log-and-continue

The validator's job is to prevent boot, not to warn. Raising propagates up through `Settings()` construction, fails `get_settings()`, and crashes the process. That's what you want: the deploy stops, the rollback triggers, the operator sees a clear error in the logs.

### Rule 3: Every error message tells the operator how to fix it

`"SECRET_KEY must be at least 32 characters"` — useful. `"invalid SECRET_KEY"` — useless. Include the command to generate a new one, the path to mount a secret, the env var name. Treat each error message as a one-line runbook.

### Rule 4: Reject placeholder secrets explicitly

The blocklist (`changeme`, `secret`, `dev`, `default`, `password`, `test`) is short and catches the cases where someone copy-pasted the example. It's not a strength check — long random strings will pass. The strength check is the length minimum. Use both.

### Rule 5: Defaults belong to dev, not prod

Every field with a default is implicitly "okay if missing in dev". Production-only rules in the validator turn those defaults into errors when `APP_ENV == "production"`. The pattern: relaxed defaults + strict production validator. Don't try to express "required in prod, optional in dev" with field types — it'll fight you.

### Rule 6: Secret-class fields use `secrets_dir`, not env vars

Mounting credentials as files at `/run/secrets/<FIELD_NAME>` is better than passing them as environment variables for three reasons:

- `docker compose config` doesn't render the values as plaintext.
- Process listings (`ps auxe`) don't leak them.
- Rotating a secret means re-mounting a file, not restarting the process with new env vars.

Pydantic-Settings reads them automatically when the `secrets_dir` config is set. Lookup order is env var → secrets file → default; document that explicitly in a comment because operators forget.

### Rule 7: The `lru_cache` on `get_settings()` is intentional

The settings object is expensive to construct (validators run, files are read) and used everywhere. Caching is correct. The cost: tests need `get_settings.cache_clear()` between env-var changes. That's the price of the pattern; pay it.

### Rule 8: `is_production` is a property, not a class constant

It's a small thing, but `is_production` should compute from `APP_ENV` at call time. Setting it as a class constant during construction means changing `APP_ENV` later in a test won't take effect.

### Rule 9: One `Settings` class, not five

Don't split `DatabaseSettings`, `AuthSettings`, `StorageSettings` into separate classes "for organization". They all share the same `APP_ENV` decision and the same validator. Section the file with comments, not separate classes.

### Rule 10: Same scheme rules for every URL, not just DB

`DATABASE_URL` must be `postgresql+asyncpg://...` in prod (asyncpg, not psycopg2 — wrong driver crashes async). `STORAGE_ENDPOINT_URL` must be `https://...` (plain HTTP for S3-compatible storage means signed-URL replay attacks). `REDIS_URL` must not be localhost in prod (obvious in retrospect, easy to ship by accident).

### Rule 11: Property accessors return parsed lists, not strings

`CORS_ALLOWED_ORIGINS` is a comma-separated string in the env, but callers need a list. Put the parsing in a property (`cors_origins`) so callers can't accidentally use the unparsed string. Same for `allowed_hosts`, trusted proxies, etc.

## Reviewing a PR that touches Settings

- [ ] Does the new field have a default? If it's secret-class, default should be `""` and the production validator should require non-empty.
- [ ] Does the new field have a corresponding production-validator branch if it's required in prod?
- [ ] Is the error message actionable (tells the operator what to set and how)?
- [ ] If the field is a comma-separated list, is there a property that returns the parsed list?
- [ ] If the field is credential-class, is it documented as living in `secrets_dir`?
- [ ] Does any test mutate env vars without calling `get_settings.cache_clear()`?
- [ ] Was the placeholder blocklist updated to catch a new common bad value (e.g., "todo", "fixme")? Usually no, but worth a thought.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| Production deploy boots with `SECRET_KEY=test` | No length check or no placeholder check |
| Application boots in prod with `DATABASE_URL=...localhost...` | Validator didn't reject localhost; add a check |
| Async DB queries crash with "MissingGreenlet" | `DATABASE_URL` is `postgresql://` not `postgresql+asyncpg://`; validator should catch |
| Operator can't figure out which env var to set | Error message lacks the field name or the suggested command |
| `docker compose config` leaks credentials | Credentials are env vars, not Docker secrets — switch to `secrets_dir` |
| Test isolation issues — config doesn't reset between tests | `get_settings()` is cached; clear the cache in test setup |
| New required setting silently defaults | Added a default to a field that should be required-in-prod — add a validator branch |

## Companion skills

- **`integration-resilience`** — tunables (`INTEGRATION_HTTP_TIMEOUT_SECONDS` etc.) belong here.
- **`fastapi-middleware-stack`** — production-only `ALLOWED_HOSTS` and CORS enforcement validated here drive middleware configuration.
