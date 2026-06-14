from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


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
    dotenv_values = _load_dotenv(PROJECT_ROOT / ".env")
    return os.getenv(name, dotenv_values.get(name, default))


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    team_max_delegations: int = _env_int("MLFORGE_TEAM_MAX_DELEGATIONS", 5)
    runtime: str = _env("MLFORGE_RUNTIME", "mock")
    codex_bin: str = _env("MLFORGE_CODEX_BIN", "codex")
    codex_model: str = _env("MLFORGE_CODEX_MODEL", "")
    codex_reasoning_effort: str = _env("MLFORGE_CODEX_REASONING_EFFORT", "")
    codex_verbosity: str = _env("MLFORGE_CODEX_VERBOSITY", "")
    codex_sandbox: str = _env("MLFORGE_CODEX_SANDBOX", "workspace-write")
    codex_timeout: int = _env_int("MLFORGE_CODEX_TIMEOUT", 1800)
    codex_inherit_proxy: bool = _env_bool("MLFORGE_CODEX_INHERIT_PROXY", True)
    codex_sandbox_provider: str = _env("MLFORGE_CODEX_SANDBOX_PROVIDER", "docker")
    codex_docker_image: str = _env("MLFORGE_CODEX_DOCKER_IMAGE", "")
    codex_docker_bin: str = _env("MLFORGE_CODEX_DOCKER_BIN", "docker")
    codex_docker_codex_bin: str = _env("MLFORGE_CODEX_DOCKER_CODEX_BIN", "codex")
    codex_docker_gpus: str = _env("MLFORGE_CODEX_DOCKER_GPUS", "")
    dataset_dir: Path = PROJECT_ROOT / _env("MLFORGE_DATASET_DIR", "data")
    kaggle_api_token: str = _env("MLFORGE_KAGGLE_API_TOKEN", "")
    kaggle_username: str = _env("MLFORGE_KAGGLE_USERNAME", "")
    kaggle_key: str = _env("MLFORGE_KAGGLE_KEY", "")


settings = Settings()
