"""Shared MongoDB connection configuration for pipeline processes."""

from __future__ import annotations

import os
from pathlib import Path


def _read_env_value(name: str) -> str | None:
    """Read a simple KEY=value entry without requiring python-dotenv."""
    env_value = os.environ.get(name)
    if env_value:
        return env_value

    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / "backend" / ".env"
    if not env_file.exists():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


MONGO_URI = _read_env_value("MONGO_URI") or "mongodb://localhost:27017"
DB_NAME = "feedback_analytics"
