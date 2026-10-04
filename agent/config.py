"""Runtime configuration loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env from the repo root, not the process cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    agent_model: str = "gpt-4o-mini"
    agent_max_steps: int = 15
    agent_retries: int = 2
    mock_app_url: str = "http://localhost:8000"
    headless: bool = True
    chaos: int = 0
    # Pause before mutating API calls (POST/PUT/PATCH/DELETE) for human approve/reject.
    require_write_approval: bool = True
    # When true, auto-answer approve on write gates (for CI / headless reviewers).
    auto_approve: bool = False
    workspace_dir: Path = Path("./workspace")
    trace_dir: Path = Path("./traces")
    log_level: str = "INFO"

    # Convenience aliases used by tools
    @property
    def base_url(self) -> str:
        return self.mock_app_url.rstrip("/")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Test helper to clear cached settings."""
    global _settings
    _settings = None
