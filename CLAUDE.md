# CLAUDE.md

Guidance for Claude Code (and humans) working on **Auto Biblio Recap**.
Follow these rules unless the user explicitly asks otherwise.

## Commands

- Manage everything with **uv**: `uv add <pkg>` (runtime), `uv add --group dev <pkg>` (tooling),
  `uv run <cmd>`. Never use `pip`, never edit `uv.lock` by hand.
- `make install` — set up the environment and pre-commit hooks.
- `make format` — auto-fix lint issues and format.
- `make check` — lint, strict typecheck, tests with coverage, strict docs build. **Run it
  before declaring any task done**; it is exactly what CI runs.
- `make docs` — serve the documentation locally.

## Architecture principles

- **Separation of concerns.** Keep domain logic pure: no I/O (files, network, database,
  environment, CLI, HTTP) in it. I/O lives at the edges and calls into the domain.
- **Thin entrypoints.** CLI commands, HTTP routes and scripts only parse input, call domain
  code and format output.
- **Object-oriented where it adds value.** Small classes with a single responsibility;
  composition over inheritance; inject dependencies through the constructor instead of
  importing globals; define abstractions as `typing.Protocol`.
- **Small units.** Short functions, cohesive modules. A file that keeps growing is doing too
  much: split it by responsibility.
- No speculative abstractions or options: build what the current task needs (YAGNI).

## Typing & data

- Type everything: parameters, return values, attributes. `pyright` runs in **strict** mode
  and must report zero errors.
- `Any`, `cast` and `# type: ignore` / `# pyright: ignore[...]` are a last resort and always
  carry a comment explaining why.
- Every piece of data crossing a boundary (configuration, API payloads, files, user input,
  third-party responses) is parsed into a **Pydantic model** and validated there.
- Prefer immutable models (`model_config = ConfigDict(frozen=True)`) and value objects.
- Never pass bare `dict`s around as implicit structures: define a model, a `TypedDict` or a
  dataclass.
- Configuration is read only through `Settings` in `config.py` (`pydantic-settings`).

## Errors

- Raise dedicated exception classes for domain errors, with explicit messages.
- Fail fast: validate early, at the boundary.
- Never swallow exceptions (`except Exception: pass`, bare `except`). Catch only what you can
  handle and re-raise with context (`raise ... from exc`).
- Use the `logging` module (configured once via `log.configure_logging`), never `print`.

## Tests

- pytest. Write the test with or before the code (TDD), and watch it fail first.
- One test module per source module (`src/auto_biblio/foo.py` → `tests/test_foo.py`).
- Test behaviour through public interfaces. Prefer real objects and fixtures over mocks;
  mock only true external boundaries.
- Coverage must stay **≥ 90 %** (branch coverage); CI fails below it.
- `examples/` holds minimal runnable scripts showing how to use the package; they are
  executed by `tests/test_examples.py`, so keep them working when the API changes.

## Docs

- Every public module, class and function has a **Google-style docstring** (enforced by
  ruff); the API reference in `docs/reference/` is generated from them.
- Update the pages in `docs/` when behaviour, commands or configuration change.
- Comments explain *why*, not *what*.

## Style

- **ruff** is the single authority for linting and formatting (`select = ["ALL"]`). Fix the
  code rather than adding ignores; a `# noqa` needs a rule code and a justification.
- Follow the naming and structure of the surrounding code.
