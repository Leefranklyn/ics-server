from __future__ import annotations

import asyncio
import os
import subprocess


def main() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    if os.getenv("SEED_DEMO_DATA", "").lower() in {"1", "true", "yes"}:
        from seed import main as seed_main

        asyncio.run(seed_main())


if __name__ == "__main__":
    main()
