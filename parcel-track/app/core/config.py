from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings

# Reject SECRET_KEY values that are obviously not real secrets.
_PLACEHOLDER_SECRETS = frozenset(
    {
        "changeme",
        "secret",
        "dev",
        "default",
        "password",
        "test",
    }
)

# Minimum acceptable length for the signing key (256 bits = 32 hex chars).
_MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_NAME: str = "ParcelTrack"
    SECRET_KEY: str

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Auth
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    INVITE_TOKEN_EXPIRE_HOURS: int = 72
    # Bcrypt cost factor. 12 is the passlib 1.7+ default; raise as hardware speeds up.
    BCRYPT_ROUNDS: int = 12

    # Storage. ACCESS_KEY_ID and SECRET_ACCESS_KEY are credentials and live
    # in Docker secrets (loaded via Settings.Config.secrets_dir below); empty
    # defaults keep host-side tests booting without a /run/secrets mount.
    # The production validator below requires non-empty values.
    STORAGE_BUCKET: str
    STORAGE_ENDPOINT_URL: str
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""
    STORAGE_REGION: str = "auto"
    STORAGE_PUBLIC_URL: str

    # Database pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 600  # recycle connections every 10 minutes
    DB_STATEMENT_TIMEOUT_MS: int = 30000  # 30-second query timeout

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Push
    EXPO_PUSH_URL: str = "https://exp.host/--/api/v2/push/send"

    # Outbound integrations — shared HTTP helper (see app/integrations/_http.py).
    INTEGRATION_HTTP_TIMEOUT_SECONDS: float = 10.0
    INTEGRATION_HTTP_RETRIES: int = 2
    INTEGRATION_CIRCUIT_BREAKER_THRESHOLD: int = 5
    INTEGRATION_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 60

    # VesselFinder polling worker (P1.5).
    # Fleet-subscription model: one /vesselslist call returns all tracked vessels,
    # so cadence is bounded by the subscription tier rather than per-call credits.
    # Disabled by default — flip the flag once secrets are wired in the hosting
    # platform AND scripts/smoke_vesselfinder.py round-trips successfully.
    VESSELFINDER_ENABLED: bool = False
    VESSELFINDER_BASE_URL: str = "https://api.vesselfinder.com"
    VESSELFINDER_FLEET_KEY: SecretStr = SecretStr("")
    VESSELFINDER_POLL_INTERVAL_MINUTES: int = 30
    # Only update Vessel.eta when the new ETA differs from the stored one by at
    # least this many hours — keeps churn off the audit log for jitter.
    VESSELFINDER_ETA_CHANGE_THRESHOLD_HOURS: int = 2
    # Trigger a "DELAYED" derived status when the revised ETA exceeds the
    # originally stored ETA by more than this many hours.
    VESSELFINDER_DELAYED_THRESHOLD_HOURS: int = 24
    # Trigger "APPROACHING" when the vessel's current position is within this
    # many nautical miles of the port_of_discharge centroid.
    VESSELFINDER_APPROACHING_RADIUS_NM: float = 50.0

    # Login lockout — Redis-backed per-account failure counter.
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_WINDOW_SECONDS: int = 900  # 15-minute sliding window

    # A/R aging (P1.4) — daily task flags containers delivered/invoiced/paid but
    # not banked, aged past the threshold. AR_AGING_ENABLED is a kill switch.
    AR_AGING_ENABLED: bool = True
    AR_AGING_THRESHOLD_DAYS: int = 14

    # Demurrage countdown alerts (P1.5) — daily task warns when free demurrage
    # time at the UK port is near expiry. DEMURRAGE_DEFAULT_FREE_DAYS is the
    # fallback when Booking.free_days_demurrage is unset.
    DEMURRAGE_ALERTS_ENABLED: bool = True
    DEMURRAGE_WARNING_LEAD_DAYS: int = 2
    DEMURRAGE_DEFAULT_FREE_DAYS: int = 5

    # Sentry error tracking.
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_ENVIRONMENT: str = ""  # defaults to APP_ENV if empty

    # Rate limiting — comma-separated trusted proxy IPs/CIDRs.
    # Only set in production behind a reverse proxy (e.g. Cloudflare).
    TRUSTED_PROXIES: str = ""

    # CORS — comma-separated list of allowed origins.
    # Example: "http://localhost:3000,https://app.parceltrack.io,https://u3-z9.exp.direct"
    # Production refuses to boot with this empty (see app/main.py).
    CORS_ALLOWED_ORIGINS: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS_ALLOWED_ORIGINS into a clean list, dropping empties/whitespace."""
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validate_settings(self) -> "Settings":
        """
        Validate settings at startup — fail fast before the app starts serving.

        SECRET_KEY strength is enforced in all environments.
        Additional production-only checks catch misconfiguration before it
        silently affects real traffic.
        """
        # ── SECRET_KEY (all envs) ─────────────────────────────────────────────
        key = self.SECRET_KEY

        if len(key) < _MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters "
                f"(got {len(key)}). Generate one with: python -c "
                '"import secrets; print(secrets.token_hex(32))"'
            )

        if key.lower().strip() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                f"SECRET_KEY looks like a placeholder ({key!r}). "
                "Set a real random value. Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )

        # ── Production-only checks ────────────────────────────────────────────
        if self.APP_ENV == "production":
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
                    "Mount via Docker secret at /run/secrets/STORAGE_ACCESS_KEY_ID."
                )

            if not self.STORAGE_SECRET_ACCESS_KEY:
                raise ValueError(
                    "STORAGE_SECRET_ACCESS_KEY must be set in production. "
                    "Mount via Docker secret at /run/secrets/STORAGE_SECRET_ACCESS_KEY."
                )

            if not self.cors_origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must be set in production. "
                    "Provide a comma-separated list of allowed origins, e.g. "
                    "'https://app.example.com,https://admin.example.com'."
                )

        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        # Pydantic-Settings reads files at this path named after each field
        # (e.g. /run/secrets/STORAGE_SECRET_ACCESS_KEY) when no env var is
        # set. Lookup order: env var → secrets file → field default. Compose
        # mounts Docker secrets here; production deploys can mount a
        # platform-managed secret store at the same path.
        secrets_dir = "/run/secrets"


@lru_cache
def get_settings() -> Settings:
    # Pydantic-Settings populates fields from env vars + secrets_dir at
    # instantiation; mypy can't see those external sources and flags every
    # field without a Python default as a missing call-arg. Suppress at
    # the construction site rather than annotating each field with
    # placeholder defaults that would change runtime validation behaviour.
    return Settings()  # type: ignore[call-arg]
