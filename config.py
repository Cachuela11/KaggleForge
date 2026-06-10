from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env(name: str, default: str = "") -> str:
    dotenv_values = _load_dotenv(Path(".env"))
    return os.getenv(name, dotenv_values.get(name, default))


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    runtime: str = _env("MLFORGE_RUNTIME", "mock")
    codex_bin: str = _env("MLFORGE_CODEX_BIN", "codex")
    codex_model: str = _env("MLFORGE_CODEX_MODEL", "")
    codex_reasoning_effort: str = _env("MLFORGE_CODEX_REASONING_EFFORT", "")
    codex_sandbox: str = _env("MLFORGE_CODEX_SANDBOX", "workspace-write")
    codex_timeout: int = _env_int("MLFORGE_CODEX_TIMEOUT", 1800)


settings = Settings()
