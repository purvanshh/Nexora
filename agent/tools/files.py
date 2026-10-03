"""Sandboxed local file read/write tool."""

from __future__ import annotations

import csv
import json
import time
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.models import Observation
from agent.tools.base import Tool


class FileArgs(BaseModel):
    action: Literal["read", "write", "list"]
    path: str = Field(description="Path relative to the workspace sandbox")
    content: Any | None = None
    format: Literal["json", "csv", "txt"] = "json"


class FileTool(Tool):
    name = "files"
    description = (
        "Read, write, or list files inside the sandbox workspace. "
        "Use for invoices, payslips, and intermediate artifacts."
    )
    args_schema = FileArgs

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel: str) -> Path:
        # Block path traversal: resolved path must stay under workspace
        candidate = (self.workspace / rel).resolve()
        if not str(candidate).startswith(str(self.workspace)):
            raise PermissionError(f"Path escapes sandbox: {rel}")
        return candidate

    async def run(self, args: BaseModel) -> Observation:
        assert isinstance(args, FileArgs)
        started = time.perf_counter()
        try:
            if args.action == "list":
                target = self._resolve(args.path or ".")
                if not target.exists():
                    return Observation(
                        ok=False,
                        error=f"Directory not found: {args.path}",
                        duration_ms=_ms(started),
                    )
                entries = sorted(p.name for p in target.iterdir())
                return Observation(
                    ok=True,
                    data={"entries": entries, "path": str(target)},
                    duration_ms=_ms(started),
                    evidence=[str(target)],
                )

            path = self._resolve(args.path)
            if args.action == "read":
                if not path.exists():
                    return Observation(
                        ok=False,
                        error=f"File not found: {args.path}",
                        duration_ms=_ms(started),
                    )
                text = path.read_text(encoding="utf-8")
                data: Any
                if path.suffix == ".json":
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError as exc:
                        return Observation(
                            ok=False,
                            error=f"Malformed JSON: {exc}",
                            duration_ms=_ms(started),
                            evidence=[str(path)],
                        )
                else:
                    data = {"text": text}
                return Observation(
                    ok=True,
                    data={"path": str(path), "content": data},
                    duration_ms=_ms(started),
                    evidence=[str(path)],
                )

            # write
            path.parent.mkdir(parents=True, exist_ok=True)
            if args.format == "json":
                path.write_text(
                    json.dumps(args.content, indent=2, default=str),
                    encoding="utf-8",
                )
            elif args.format == "csv":
                buf = StringIO()
                rows = args.content
                if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
                    path.write_text(buf.getvalue(), encoding="utf-8")
                else:
                    path.write_text(str(args.content), encoding="utf-8")
            else:
                path.write_text(str(args.content), encoding="utf-8")

            return Observation(
                ok=True,
                data={"path": str(path), "written": True},
                duration_ms=_ms(started),
                evidence=[str(path)],
            )
        except Exception as exc:  # noqa: BLE001 — surface as Observation
            return Observation(ok=False, error=str(exc), duration_ms=_ms(started))


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
