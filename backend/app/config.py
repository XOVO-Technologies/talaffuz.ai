"""Paths and environment-driven configuration."""
from __future__ import annotations

import os
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
ENV_FILE = Path(os.environ.get("URDU_ENV_FILE") or BACKEND_DIR / ".env")  # git-ignored
KEY_NAME = "ANTHROPIC_API_KEY"
KEY_PATTERN = re.compile(r"[A-Za-z0-9_\-]{20,300}")  # no spaces, quotes or newlines, so it is safe to write to .env


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader so ANTHROPIC_API_KEY can live in backend/.env."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ENV_FILE)


def _env_lines() -> list[str]:
    return ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []


def _saved_key() -> str:
    for line in _env_lines():
        name, _, value = line.partition("=")
        if name.strip() == KEY_NAME:
            return value.strip().strip('"').strip("'")
    return ""


def _write_env_value(name: str, value: str) -> None:
    """Set one line in backend/.env, keeping every other line. An empty value blanks the line."""
    lines, found = [], False
    for line in _env_lines():
        if line.partition("=")[0].strip() == name:
            lines.append(f"{name}={value}")
            found = True
        else:
            lines.append(line)
    if not found:
        if not value:
            return
        lines.append(f"{name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def key_status() -> dict:
    """What the UI may know about the API key: never the key itself."""
    return {
        "configured": bool(os.environ.get(KEY_NAME) or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
        "saved": bool(_saved_key()),
        "model": ROMANIZE_MODEL,
    }


def save_api_key(key: str, remember: bool) -> None:
    os.environ[KEY_NAME] = key
    if remember:
        _write_env_value(KEY_NAME, key)


def clear_api_key() -> None:
    os.environ.pop(KEY_NAME, None)
    _write_env_value(KEY_NAME, "")


def set_romanize_model(model: str, remember: bool) -> None:
    global ROMANIZE_MODEL
    ROMANIZE_MODEL = model
    if remember:
        _write_env_value("ROMANIZE_MODEL", model)

DATA_DIR = Path(os.environ.get("DATASET_DATA_DIR") or ROOT_DIR / "data").resolve()
PROJECTS_DIR = DATA_DIR / "projects"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

MAX_UPLOAD_BYTES = int(float(os.environ.get("MAX_UPLOAD_GB", "8")) * 1024**3)
# The lowest-cost current Claude model. Turning Urdu into Roman Urdu is a short, rule-following task, so it is the default.
ROMANIZE_MODEL = os.environ.get("ROMANIZE_MODEL", "claude-haiku-5-5")
