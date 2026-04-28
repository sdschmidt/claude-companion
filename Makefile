.PHONY: dev sync lint fmt typecheck checkall test clean

sync:				## Install / update dependencies
	uv sync

dev:				## Run the desktop companion
	uv run companion

dev-debug:			## Run with debug logging to stderr
	uv run companion --debug

lint:
	uv run ruff check --fix .

fmt:
	uv run ruff format .

typecheck:
	uv run pyright src

test:
	uv run pytest

checkall: fmt lint typecheck test

clean:
	rm -rf dist/ build/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
