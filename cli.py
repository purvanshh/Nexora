"""CLI entrypoint for the autonomous AI task worker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from agent.config import get_settings, reset_settings
from agent.loop import run
from agent.tracer import Tracer

app = typer.Typer(add_completion=False, help="Nexora autonomous AI task worker")
console = Console()

PRIMARY_TASK = (
    "Find the latest invoice from Acme Corp in the mail app, extract amount and "
    "due date, enter it into the finance system, and confirm it's saved."
)


@app.command()
def main(
    task: Optional[str] = typer.Argument(None, help="Natural-language task"),
    max_steps: int = typer.Option(15, "--max-steps", help="Hard cap on ReAct steps"),
    no_headless: bool = typer.Option(False, "--no-headless", help="Show browser UI"),
    trace: Optional[Path] = typer.Option(None, "--trace", help="Optional trace file path"),
    model: Optional[str] = typer.Option(None, "--model", help="Override AGENT_MODEL"),
) -> None:
    """Run one autonomous task against the local mock environment."""
    reset_settings()
    settings = get_settings()
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-..."):
        console.print(
            "[red]OPENAI_API_KEY missing.[/red] Copy `.env.example` → `.env` and set it "
            "before booting the agent."
        )
        raise typer.Exit(code=2)
    if no_headless:
        settings.headless = False
    if model:
        settings.agent_model = model
    settings.agent_max_steps = max_steps

    task_text = task or PRIMARY_TASK
    tracer: Tracer | None = None
    if trace is not None:
        trace.parent.mkdir(parents=True, exist_ok=True)
        tracer = Tracer(run_id=trace.stem, trace_dir=trace.parent)

    async def _go() -> None:
        try:
            result = await run(
                task_text,
                max_steps=max_steps,
                settings=settings,
                tracer=tracer,
            )
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc

        elapsed = (result.ended_at - result.started_at).total_seconds()
        icon = {"success": "✓", "partial": "⚠", "failed": "✗"}[result.status]
        console.print(
            f"\n[bold]{icon} Task {result.status}[/bold] "
            f"({len(result.steps)} steps, {elapsed:.1f}s)\n"
        )
        console.print(Panel(result.summary or "(no summary)", title="Summary"))
        if result.verification:
            v = result.verification
            console.print(
                f"\nVerification: {'passed' if v.passed else 'failed'} "
                f"via {v.method}"
            )
            for check in v.checks:
                console.print(f"  • {check}")
        if result.evidence_paths:
            console.print("\nEvidence:")
            for path in result.evidence_paths:
                console.print(f"  - {path}")
        if tracer:
            console.print(f"\nTrace: {tracer.path}")
        raise typer.Exit(code=0 if result.status == "success" else 1)

    asyncio.run(_go())


if __name__ == "__main__":
    app()
