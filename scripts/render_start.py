from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def validate_render_environment() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add your Render Postgres Internal Database URL to the web service environment.")

    parsed_database_url = urlparse(database_url)
    if os.getenv("RENDER") and parsed_database_url.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(
            "DATABASE_URL points to localhost. On Render, set DATABASE_URL to your Render Postgres Internal Database URL."
        )


def run_migrations() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True)


def seed_demo_data_if_enabled() -> None:
    if os.getenv("SEED_DEMO_DATA", "").lower() not in {"1", "true", "yes"}:
        return

    from seed import main as seed_main

    asyncio.run(seed_main())


def main() -> None:
    validate_render_environment()
    run_migrations()
    seed_demo_data_if_enabled()

    uvicorn.run(
        "ics_backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
    )


if __name__ == "__main__":
    main()
