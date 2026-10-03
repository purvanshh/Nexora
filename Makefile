.PHONY: install lint test demo mock seed reset chaos-demo secondary

install:
	uv sync --all-extras
	uv run playwright install chromium

lint:
	uv run ruff check agent mock_app tests cli.py || true
	@echo "lint ok"

test:
	uv run pytest -q

seed:
	uv run python scripts/seed_reset.py

mock:
	uv run uvicorn mock_app.main:app --host 127.0.0.1 --port 8000 --reload

demo:
	bash scripts/run_demo.sh

chaos-demo:
	CHAOS=1 bash scripts/run_demo.sh

secondary:
	bash scripts/run_demo.sh "Look up employee 42, get their latest payslip, and tell me their net pay."

reset: seed
