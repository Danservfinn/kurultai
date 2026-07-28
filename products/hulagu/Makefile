.PHONY: sync test contract integration lint typecheck security verify-gate

sync:
	uv sync --frozen

test:
	uv run pytest -q

contract:
	uv run pytest tests/contract -vv

integration:
	uv run pytest tests/integration -vv

lint:
	uv run ruff check src deploy tests

typecheck:
	uv run mypy src deploy/scripts

security:
	uv run bandit -q -r src deploy/scripts

verify-gate:
	uv run hulagu-verify-plan-gate
