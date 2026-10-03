"""Runtime configuration loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
