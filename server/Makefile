.PHONY: test lint lint-fix typecheck format check help

help:
	@echo "Targets:"
	@echo "  test       - Run the test suite"
	@echo "  lint       - Lint with ruff"
	@echo "  lint-fix   - Lint and auto-fix with ruff"
	@echo "  format     - Auto-format with ruff"
	@echo "  typecheck  - Type-check with mypy"
	@echo "  check      - CI: lint + typecheck + test"

test:
	uv run pytest

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

typecheck:
	uv run mypy app

check: lint typecheck test
