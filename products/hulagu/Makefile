.PHONY: sync test contract lint security verify-plan doctor

sync:
	uv sync --frozen

test:
	uv run pytest -vv

contract:
	uv run pytest tests/contract tests/integration/test_vault_preflight.py tests/integration/test_container_mount_probe.py -vv

lint:
	uv run ruff check src deploy tests

security:
	uv run bandit -c pyproject.toml -r src deploy
	uv run pip-audit

verify-plan:
	uv run hulagu-verify-plan-gate

doctor:
	uv run hulagu-doctor
