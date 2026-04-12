from functools import lru_cache

from pydantic import model_validator
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

    # Storage
    STORAGE_BUCKET: str
    STORAGE_ENDPOINT_URL: str
    STORAGE_ACCESS_KEY_ID: str
    STORAGE_SECRET_ACCESS_KEY: str
    STORAGE_REGION: str = "auto"
    STORAGE_PUBLIC_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Push
    EXPO_PUSH_URL: str = "https://exp.host/--/api/v2/push/send"

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
    def _validate_secret_key(self) -> "Settings":
        """
        Reject SECRET_KEY values that are too short or obviously placeholder.

        Enforced in ALL environments (including development) — a weak dev
        key is a footgun that will eventually leak into staging or prod.
        """
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

        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
