.PHONY: install format lint typecheck test docs docs-build check

install:
	uv sync --all-groups
	@if [ -d .git ]; then uv run pre-commit install; \
	else echo "No git repository: run 'git init' then 'make install' again to enable pre-commit hooks."; fi

format:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run pyright

test:
	uv run pytest --cov --cov-report=term-missing --cov-report=xml --cov-report=html

docs:
	uv run python scripts/gen_ref_pages.py
	uv run zensical serve --dev-addr localhost:8001

docs-build:
	uv run python scripts/gen_ref_pages.py
	uv run zensical build --strict --clean

check: lint typecheck test docs-build
