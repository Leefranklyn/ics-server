from __future__ import annotations

import asyncio
import os
import subprocess

import uvicorn


def run_migrations() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True)


def seed_demo_data_if_enabled() -> None:
    if os.getenv("SEED_DEMO_DATA", "").lower() not in {"1", "true", "yes"}:
        return

    from seed import main as seed_main

    asyncio.run(seed_main())


def main() -> None:
    run_migrations()
    seed_demo_data_if_enabled()

    uvicorn.run(
        "ics_backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
    )


if __name__ == "__main__":
    main()
