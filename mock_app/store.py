"""JSON-backed persistence for the mock company system."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
SEED_DIR = Path(__file__).resolve().parent / "seed"


def _ensure_seed_copies() -> None:
    """Keep immutable seed snapshots for reset."""
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("emails.json", "invoices.json", "employees.json", "payslips.json"):
        seed_path = SEED_DIR / name
        data_path = DATA_DIR / name
        if not seed_path.exists() and data_path.exists():
            shutil.copy2(data_path, seed_path)


def reset_data() -> None:
    _ensure_seed_copies()
    for name in ("emails.json", "invoices.json", "employees.json", "payslips.json"):
        src = SEED_DIR / name
        dst = DATA_DIR / name
        if src.exists():
            shutil.copy2(src, dst)


def read_json(name: str) -> Any:
    path = DATA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, data: Any) -> None:
    path = DATA_DIR / name
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


# Initialize seed snapshots on import
_ensure_seed_copies()
