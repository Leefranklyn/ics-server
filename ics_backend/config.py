from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ics_backend",
    )
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-this-development-secret")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ESP32_API_KEY: str = os.getenv("ESP32_API_KEY", "development-esp32-api-key")
    DEFAULT_CARD_PASSWORD: str = os.getenv("DEFAULT_CARD_PASSWORD", "ChangeMe123!")
    CORS_ALLOW_ORIGINS: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "DATABASE_URL", _normalize_database_url(self.DATABASE_URL))
        raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
        origins = ["*"] if raw_origins == "*" else [item.strip() for item in raw_origins.split(",") if item.strip()]
        object.__setattr__(self, "CORS_ALLOW_ORIGINS", origins)


settings = Settings()
