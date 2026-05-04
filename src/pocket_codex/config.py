from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class ProjectConfig:
    id: str
    name: str
    path: Path | None = None
    system_prompt: str = ""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    openai_model: str
    openai_store: bool
    data_dir: Path
    database_path: Path
    projects_file: Path
    projects: tuple[ProjectConfig, ...]
    allowed_user_ids: frozenset[int]
    setup_token: str | None
    max_history_messages: int
    codex_sync_enabled: bool
    codex_home: Path


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = _required("TELEGRAM_BOT_TOKEN")
    openai_api_key = _required("OPENAI_API_KEY")
    data_dir = Path(os.getenv("POCKET_CODEX_DATA_DIR", "./data")).expanduser().resolve()
    database_path = Path(os.getenv("DATABASE_PATH", data_dir / "pocket_codex.sqlite3"))
    projects_file = Path(os.getenv("POCKET_CODEX_PROJECTS_FILE", "./config/projects.json"))

    if not database_path.is_absolute():
        database_path = database_path.resolve()
    if not projects_file.is_absolute():
        projects_file = projects_file.resolve()

    settings = Settings(
        telegram_bot_token=telegram_bot_token,
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        openai_store=_bool_env("OPENAI_STORE", default=False),
        data_dir=data_dir,
        database_path=database_path,
        projects_file=projects_file,
        projects=tuple(_load_projects(projects_file)),
        allowed_user_ids=frozenset(_int_set_env("TELEGRAM_ALLOWED_USER_IDS")),
        setup_token=_optional("BOT_SETUP_TOKEN"),
        max_history_messages=_int_env("MAX_HISTORY_MESSAGES", default=24, minimum=4),
        codex_sync_enabled=_bool_env("CODEX_SYNC_ENABLED", default=True),
        codex_home=Path(
            os.getenv("CODEX_HOME", Path.home() / ".codex")
        ).expanduser().resolve(),
    )
    return settings


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, *, default: int, minimum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return value


def _int_set_env(name: str) -> set[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError as exc:
            raise ConfigError(
                f"{name} must contain comma-separated numeric Telegram user ids."
            ) from exc
    return values


def _load_projects(path: Path) -> list[ProjectConfig]:
    if not path.exists():
        return [
            ProjectConfig(
                id="general",
                name="General Chat",
                path=None,
                system_prompt=(
                    "General personal conversation. Answer in the user's preferred language."
                ),
            )
        ]

    try:
        raw_projects = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid projects JSON: {path}") from exc

    if not isinstance(raw_projects, list):
        raise ConfigError("Projects file must contain a JSON array.")

    projects: list[ProjectConfig] = []
    seen_ids: set[str] = set()
    for raw in raw_projects:
        if not isinstance(raw, dict):
            raise ConfigError("Each project entry must be an object.")
        project_id = str(raw.get("id", "")).strip()
        name = str(raw.get("name", "")).strip()
        if not project_id or not name:
            raise ConfigError("Each project needs a non-empty id and name.")
        if project_id in seen_ids:
            raise ConfigError(f"Duplicate project id: {project_id}")
        seen_ids.add(project_id)

        raw_path = raw.get("path")
        project_path = (
            None
            if raw_path in (None, "")
            else Path(str(raw_path)).expanduser().resolve()
        )
        projects.append(
            ProjectConfig(
                id=project_id,
                name=name,
                path=project_path,
                system_prompt=str(raw.get("system_prompt", "")).strip(),
            )
        )

    if not projects:
        raise ConfigError("At least one project must be configured.")
    return projects
