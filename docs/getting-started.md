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
| `config/llm.yaml` | Models used by the triage, fallback chain and weekly budget |
| `config/triage.yaml` | Every decision constant of the triage (see [Triage](triage.md)) |
| `.github/workflows/daily.yml` | Daily collection, signal refresh and feedback ingestion at 05:00 UTC |
| `.github/workflows/weekly.yml` | Weekly triage and digest, Sunday 05:30 UTC |
| `.gitignore`, `state/.gitkeep` | Repository skeleton |

Push it to a **private** GitHub repository: the workflow commits `state/` after each run,
including the run report when every source failed.

!!! warning "Prerequisites for the daily workflow"
    The workflow installs `git+https://github.com/ocoudray/auto-biblio@v<version>`, the version
    you ran `init` with. That tag must exist on GitHub, and this code repository must be public
    (otherwise the workflow needs a read token for it). Push the tag before the first scheduled
    run, for example `git tag v0.1.0 && git push origin v0.1.0`.

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

## Triage and digest

```bash
auto-biblio signals refresh              # re-read stars and upvotes of recent items
auto-biblio feedback ingest              # record the 👍/👎 issues and close them
auto-biblio triage                       # rank this week's items (LLM, within budget)
auto-biblio triage --week 2026-W41       # re-run a week: cached answers cost nothing
auto-biblio digest --dry-run digest.html # render without mailing
auto-biblio digest                       # mail the latest triaged week
auto-biblio eval scoring                 # fixed vs learned scoring, on reliable labels
auto-biblio health                       # fail if no triage ran for alert_after_days
```

| Exit code | Meaning |
|---|---|
| 1 | Invalid or missing configuration, or no triage for the requested week |
| 3 | `health`: the weekly triage has not run for too long |
| 4 | `digest`: the mail could not be sent |

See [Triage](triage.md) for how items are ranked, and [Upgrade to 0.2](upgrade-0.2.md) to set
up an existing data repository.

## Configuration

Settings are read from environment variables prefixed with `AUTO_BIBLIO_`,
or from a `.env` file (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `AUTO_BIBLIO_DATA_DIR` | `.` | Data repository root |
| `AUTO_BIBLIO_GITHUB_TOKEN` | unset | Raises the GitHub API rate limit (set automatically in the workflow) |
| `AUTO_BIBLIO_HTTP_TIMEOUT_S` | `30` | HTTP timeout per request |
| `AUTO_BIBLIO_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `AUTO_BIBLIO_DATA_REPO` | unset | `owner/repo` of the data repository: feedback links and issues |
| `AUTO_BIBLIO_GEMINI_API_KEY` | unset | Google AI Studio key (models `google:…`) |
| `AUTO_BIBLIO_ANTHROPIC_API_KEY` | unset | Anthropic key (models `anthropic:…`) |
| `AUTO_BIBLIO_SMTP_HOST` / `_SMTP_PORT` | `smtp.gmail.com` / `465` | SMTP server (implicit TLS) |
| `AUTO_BIBLIO_SMTP_USER` / `_SMTP_PASSWORD` | unset | SMTP login (a Gmail application password) |
| `AUTO_BIBLIO_DIGEST_TO` | unset | Recipient of the digest |
| `AUTO_BIBLIO_EMBEDDINGS_CACHE_DIR` | `.cache/embeddings` | Embedding cache, relative to the data repository |

## Develop

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
make install   # .venv with every dependency group + pre-commit hooks
make check     # lint, strict typecheck, tests (coverage >= 90 %), strict docs build
uv run python examples/dedup.py     # cross-source deduplication, offline
uv run python examples/scoring.py   # fair ranking across source families, offline
```

| Command | What it does |
|---|---|
| `make format` | Auto-fix lint issues and format the code |
| `make lint` | ruff checks and format check |
| `make typecheck` | pyright (strict) |
| `make test` | pytest with coverage (fails under 90 %) |
| `make docs` | Serve this documentation locally with live reload |
| `make check` | Everything CI runs: lint, typecheck, test, strict docs build |
