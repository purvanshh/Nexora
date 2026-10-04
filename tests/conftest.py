"""Shared fixtures: live mock app, temp workspace, reset seed data."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest

from agent.config import Settings, reset_settings
from mock_app.routers.finance import reset_chaos
from mock_app.store import reset_data

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _boot_mock_app(*, env_extra: dict[str, str] | None = None) -> Generator[str, None, None]:
    reset_data()
    reset_chaos()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["CHAOS"] = "0"
    env["PERMANENT_FAIL"] = "0"
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "mock_app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        for _ in range(50):
            try:
                r = httpx.get(f"{base}/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            proc.kill()
            raise RuntimeError("mock_app failed to start")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        reset_data()
        reset_chaos()


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture()
def settings(workspace: Path, tmp_path: Path) -> Settings:
    reset_settings()
    s = Settings(
        openai_api_key="test-key",
        mock_app_url="http://127.0.0.1:9",
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
        headless=True,
        chaos=0,
    )
    s.trace_dir.mkdir(parents=True, exist_ok=True)
    return s


@pytest.fixture()
def mock_app() -> Generator[str, None, None]:
    """Boot uvicorn against mock_app.main on a free port; reset data each test."""
    yield from _boot_mock_app()


@pytest.fixture()
def mock_app_permanent_fail() -> Generator[str, None, None]:
    """Mock app where every invoice POST returns 500."""
    yield from _boot_mock_app(env_extra={"PERMANENT_FAIL": "1", "CHAOS": "0"})
