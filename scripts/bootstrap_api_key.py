"""Create one production API key and write its secret to a protected file."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.production.auth import api_key_locator, generate_api_key, hash_api_key
from app.production.models import ApiKey, create_engine


async def _create_key(
    name: str,
    scopes: list[str],
    raw_key: str,
    expires_days: int,
) -> None:
    """Insert a hashed API key record."""
    settings.validate_runtime()
    locator = api_key_locator(raw_key)
    if locator is None:
        raise ValueError("generated API key has an invalid locator")
    record = ApiKey(
        name=name,
        key_prefix=locator,
        key_hash=hash_api_key(raw_key, settings.api_key_pepper),
        scopes=scopes,
        active=True,
        expires_at=datetime.now(UTC) + timedelta(days=expires_days),
    )
    engine = create_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            session.add(record)
            await session.commit()
    finally:
        await engine.dispose()


def _write_secret(path: Path, raw_key: str) -> None:
    """Write a new credential file with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(f"{raw_key}\n")
        path.chmod(0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _main() -> int:
    """Parse key metadata and create the credential."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="human-readable owner or integration name")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=[],
        help="repeat for each scope, for example jobs:read",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        type=Path,
        help="new file that receives the one-time raw key",
    )
    parser.add_argument(
        "--expires-days",
        type=int,
        default=90,
        metavar="DAYS",
        help="credential lifetime in days (default: 90, maximum: 3660)",
    )
    args = parser.parse_args()
    if not 1 <= args.expires_days <= 3660:
        parser.error("--expires-days must be between 1 and 3660")
    scopes = args.scopes or [
        "agent:plan",
        "generate",
        "jobs:read",
        "jobs:write",
        "vision",
        "artifacts:read",
    ]
    raw_key = generate_api_key()
    _write_secret(args.output_file, raw_key)
    try:
        asyncio.run(_create_key(args.name, scopes, raw_key, args.expires_days))
    except BaseException:
        args.output_file.unlink(missing_ok=True)
        raise
    print(f"API key created and written to {args.output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
