# Getting started

## Requirements

- [uv](https://docs.astral.sh/uv/) (manages Python 3.12+, dependencies and tools)
- `make`

## Install

```bash
make install
```

This creates `.venv/` with every dependency group and installs the pre-commit hooks.
Commit the generated `uv.lock`: CI installs with `uv sync --locked`.

## Try it

Each enabled use case ships a minimal, runnable example:

```bash
uv run python examples/quickstart.py   # library: call the core logic
```

## Daily commands

| Command | What it does |
|---|---|
| `make format` | Auto-fix lint issues and format the code |
| `make lint` | ruff checks and format check |
| `make typecheck` | pyright (strict) |
| `make test` | pytest with coverage (fails under 90 %) |
| `make docs` | Serve this documentation locally with live reload |
| `make check` | Everything CI runs: lint, typecheck, test, strict docs build |

## Configuration

Settings are read from environment variables prefixed with `AUTO_BIBLIO_`,
or from a `.env` file (see `.env.example`).
