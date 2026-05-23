from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = _required_env("DATABASE_URL")
    JWT_SECRET_KEY: str = _required_env("JWT_SECRET_KEY")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ESP32_API_KEY: str = _required_env("ESP32_API_KEY")
    DEFAULT_CARD_PASSWORD: str = _required_env("DEFAULT_CARD_PASSWORD")
    CORS_ALLOW_ORIGINS: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "DATABASE_URL", _normalize_database_url(self.DATABASE_URL))
        raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
        origins = ["*"] if raw_origins == "*" else [item.strip() for item in raw_origins.split(",") if item.strip()]
        object.__setattr__(self, "CORS_ALLOW_ORIGINS", origins)


settings = Settings()
