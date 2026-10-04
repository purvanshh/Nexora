.PHONY: install lint test demo primary secondary leave-demo chaos-demo escalate-demo mock seed reset check-scripts

PRIMARY_TASK := Find the latest invoice from Acme Corp in the mail app, extract amount and due date, enter it into the finance system, and confirm it is saved.
SECONDARY_TASK := Look up employee 42, get their latest payslip, and tell me their net pay.
LEAVE_TASK := File a leave request for employee 42 from 2025-04-01 to 2025-04-05 with reason family.

install:
	uv sync --all-extras
	uv run playwright install chromium

check-scripts:
	bash -n scripts/run_demo.sh

lint: check-scripts
	uv run ruff check agent mock_app tests cli.py || true
	@echo "lint ok"

test:
	uv run pytest -q

seed:
	uv run python scripts/seed_reset.py

mock:
	uv run uvicorn mock_app.main:app --host 127.0.0.1 --port 8000 --reload

# All agent targets go through run_demo.sh so the mock server lifecycle is consistent.
demo primary:
	bash scripts/run_demo.sh "$(PRIMARY_TASK)"

secondary:
	bash scripts/run_demo.sh "$(SECONDARY_TASK)"

# Second write-type task (HR leave). Approve the POST when prompted.
leave-demo:
	bash scripts/run_demo.sh "$(LEAVE_TASK)"

chaos-demo:
	CHAOS=1 bash scripts/run_demo.sh "$(PRIMARY_TASK)"

# Every invoice POST returns 500 — approve the write (`a`), then abort on escalate (`a`).
escalate-demo:
	PERMANENT_FAIL=1 bash scripts/run_demo.sh "$(PRIMARY_TASK)"

reset: seed
