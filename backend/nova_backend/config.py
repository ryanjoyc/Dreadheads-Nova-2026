"""Configuration is read once at the process boundary."""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_storage_path: Path
    cors_origins: list[str]


@lru_cache
def get_settings() -> Settings:
    database_url = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://nova:nova_local@db:5432/nova_sales"
    )
    try:
        url = make_url(database_url)
        if url.drivername != "postgresql+psycopg":
            raise ValueError
    except Exception:
        raise ValueError("DATABASE_URL must use postgresql+psycopg") from None
    try:
        origins = json.loads(os.getenv("CORS_ORIGINS", '["http://localhost:3000"]'))
        if not isinstance(origins, list) or not all(isinstance(v, str) for v in origins):
            raise ValueError
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"localhost", "127.0.0.1"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
            _ = parsed.port  # Reject malformed ports before passing them to CORS.
    except (ValueError, TypeError):
        raise ValueError("CORS_ORIGINS must be a JSON list of localhost origins") from None
    return Settings(
        database_url=database_url,
        raw_storage_path=Path(os.getenv("RAW_STORAGE_PATH", "/raw")),
        cors_origins=origins,
    )
