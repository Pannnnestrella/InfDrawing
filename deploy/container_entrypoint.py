"""Resolve Compose secret files into application environment variables."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote


def load_secret(variable: str) -> None:
    """Load VARIABLE from VARIABLE_FILE when present."""
    file_name = os.getenv(f"{variable}_FILE")
    if file_name:
        os.environ[variable] = Path(file_name).read_text(encoding="utf-8").strip()


def configure_database_url() -> None:
    """Build an escaped async PostgreSQL URL from component settings."""
    if os.getenv("INFD_DATABASE_URL"):
        return
    load_secret("INFD_DATABASE_PASSWORD")
    password = os.getenv("INFD_DATABASE_PASSWORD")
    if not password:
        return
    user = quote(os.environ["INFD_DATABASE_USER"], safe="")
    escaped_password = quote(password, safe="")
    host = os.getenv("INFD_DATABASE_HOST", "postgres")
    port = os.getenv("INFD_DATABASE_PORT", "5432")
    database = quote(os.getenv("INFD_DATABASE_NAME", "infdrawing"), safe="")
    os.environ["INFD_DATABASE_URL"] = (
        f"postgresql+asyncpg://{user}:{escaped_password}@{host}:{port}/{database}"
    )


def main() -> None:
    """Prepare the environment and execute the container command."""
    load_secret("INFD_S3_SECRET_KEY")
    load_secret("INFD_API_KEY_PEPPER")
    load_secret("INFD_OPENAI_API_KEY")
    configure_database_url()
    if len(sys.argv) < 2:
        raise SystemExit("container command is required")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
