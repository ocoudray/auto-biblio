# Getting started

## Two repositories

- **This repository** holds the `auto-biblio` package and its command-line tool. It contains no data.
- **A data repository** (private) holds your configuration (`config/`), the collected
  state (`state/`) and the GitHub Actions workflow that runs the collection every day.
  `auto-biblio init` creates it.

## Install the tool

```bash
uv tool install git+https://github.com/ocoudray/auto-biblio
```

## Create a data repository

```bash
auto-biblio init ~/auto-biblio-data
cd ~/auto-biblio-data
auto-biblio validate-config
```

`init` writes:

| File | Purpose |
|---|---|
| `config/profile.yaml` | Interest profile: themes, keywords, watched repositories |
| `config/sources.yaml` | Sources to poll; add an entry to add a feed, an arXiv category… |
| `.github/workflows/daily.yml` | Daily collection at 05:00 UTC, pinned to the installed version |
| `.gitignore`, `state/.gitkeep` | Repository skeleton |

Push it to a **private** GitHub repository: the workflow commits `state/` after each run.

## Collect

```bash
auto-biblio collect                      # every enabled source
auto-biblio collect --source arxiv       # one source (repeatable)
auto-biblio collect --since 2026-09-01   # override the cursors
```

| Exit code | Meaning |
|---|---|
| 0 | At least one source succeeded |
| 1 | Invalid configuration (the message names the file and field) |
| 2 | Every source failed |

Results land in `state/`:

| Path | Content |
|---|---|
| `state/items/YYYY-MM.jsonl` | Deduplicated items, by month first seen, sorted by id |
| `state/signals/YYYY-MM.jsonl` | Stars, upvotes, points, comments (one per item, kind and day) |
| `state/cursors.json` | Last successful run of each source |
| `state/runs/<run>.json` | Per-source report of each run |
| `state/quarantine/<run>/<source>.txt` | Payloads a source failed to parse |

A second run on the same day changes nothing in `items/` and `signals/`.

## Configuration

Settings are read from environment variables prefixed with `AUTO_BIBLIO_`,
or from a `.env` file (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `AUTO_BIBLIO_DATA_DIR` | `.` | Data repository root |
| `AUTO_BIBLIO_GITHUB_TOKEN` | unset | Raises the GitHub API rate limit (set automatically in the workflow) |
| `AUTO_BIBLIO_HTTP_TIMEOUT_S` | `30` | HTTP timeout per request |
| `AUTO_BIBLIO_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

## Develop

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
make install   # .venv with every dependency group + pre-commit hooks
make check     # lint, strict typecheck, tests (coverage >= 90 %), strict docs build
uv run python examples/dedup.py   # cross-source deduplication, offline
```

| Command | What it does |
|---|---|
| `make format` | Auto-fix lint issues and format the code |
| `make lint` | ruff checks and format check |
| `make typecheck` | pyright (strict) |
| `make test` | pytest with coverage (fails under 90 %) |
| `make docs` | Serve this documentation locally with live reload |
| `make check` | Everything CI runs: lint, typecheck, test, strict docs build |
