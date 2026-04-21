from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Dhan API
    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""
    DHAN_BASE_URL: str = "https://api.dhan.co/v2"
    DHAN_WS_URL: str = "wss://api-feed.dhan.co"
    # Auto token refresh — set these to never update DHAN_ACCESS_TOKEN manually
    DHAN_PIN: str = ""           # 6-digit numeric PIN
    DHAN_TOTP_SECRET: str = ""   # base32 TOTP secret

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:80"

    # Risk-free rate (RBI repo rate approx)
    RISK_FREE_RATE: float = 0.065

    # Market config
    NIFTY_SECURITY_ID: str = "13"
    BANKNIFTY_SECURITY_ID: str = "25"
    DEFAULT_INDEX: str = "NIFTY"
    EXCHANGE_SEGMENT: str = "IDX_I"

    # ── Auth ──────────────────────────────────────────────────────────────────
    # Secret key for JWT signing — change this in production!
    JWT_SECRET: str = "optionsdesk-super-secret-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480   # 8 hours

    # Invite code required at signup — owner distributes this
    INVITE_CODE: str = "OPTDESK2026"

    # Max concurrent sessions per user (1 = single-device enforcement)
    MAX_SESSIONS_PER_USER: int = 1

    # ── Admin Panel ───────────────────────────────────────────────────────────
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "OptionsDesk@Admin2026"
    ADMIN_JWT_SECRET: str = "admin-super-secret-key-change-in-production-2026"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
