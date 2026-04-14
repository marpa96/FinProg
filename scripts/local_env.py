"""Small .env loader for local scripts.

The repo avoids a dotenv dependency, so scripts that need local secrets can use
this parser for simple KEY=value files.
"""

from __future__ import annotations

import os
from pathlib import Path


def strip_env_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path, override: bool = False) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        parsed_value = strip_env_quotes(value)
        loaded[key] = parsed_value
        if override or key not in os.environ:
            os.environ[key] = parsed_value

    return loaded


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Set KEY=value pairs in a local .env file, preserving unrelated lines."""
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining_updates = dict(updates)
    output_lines: list[str] = []

    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            output_lines.append(raw_line)
            continue

        key = raw_line.split("=", 1)[0].strip()
        if key in remaining_updates:
            value = remaining_updates.pop(key)
            output_lines.append(f"{key}={value}")
            os.environ[key] = value
        else:
            output_lines.append(raw_line)

    for key, value in remaining_updates.items():
        output_lines.append(f"{key}={value}")
        os.environ[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
