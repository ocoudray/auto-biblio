# Auto Biblio Recap

[![CI](https://github.com/ocoudray/auto-biblio/actions/workflows/ci.yml/badge.svg)](https://github.com/ocoudray/auto-biblio/actions/workflows/ci.yml)
[![Coverage](https://ocoudray.github.io/auto-biblio/badges/coverage.svg)](https://ocoudray.github.io/auto-biblio/coverage-report/)
[![Docs](https://img.shields.io/badge/docs-zensical-blue)](https://ocoudray.github.io/auto-biblio/)

An automated watch on AI research and engineering. It collects new papers, repositories,
releases, blog posts and discussions (arXiv, Hugging Face Daily Papers, GitHub, Hacker News,
RSS), deduplicates them across sources and stores them in a separate data repository. Every
week it triages them against your interest profile, with local embeddings and a cheap LLM
within a budget, writes notes and theme pages into a knowledge base, and mails a short digest
whose 👍/👎 links train the ranking. The site and the local assistant come in the next
sub-projects (see the
[vision](docs/superpowers/specs/2026-10-10-auto-biblio-vision-design.md)).

## Set up

Two repositories work together:

- **`auto-biblio`** (this one, public): the package and its `auto-biblio` command. No data.
- **A data repository** (private, e.g. `auto-biblio-data`): your configuration, the collected
  state and the GitHub Actions workflow that runs the collection every day.

```bash
uv tool install git+https://github.com/ocoudray/auto-biblio@v0.5.0
auto-biblio init ~/auto-biblio-data          # writes config/, state/, .github/workflows/
cd ~/auto-biblio-data && auto-biblio validate-config
git init -b main && git add -A && git commit -m "chore: init data repository"
gh repo create <you>/auto-biblio-data --private --source=. --push
```

The daily workflow then runs at 05:00 UTC and the weekly one on Sunday at 05:30 UTC; trigger
them by hand from the data repository's **Actions** tab. The weekly triage needs API keys and
SMTP credentials: see [Upgrade to 0.2](docs/upgrade-0.2.md) for the secrets to add, and
[Triage](docs/triage.md) for how items are ranked.

## How it works

### The daily run

`.github/workflows/daily.yml` (in the data repository) does five things:

1. Checks out the data repository (configuration and current `state/`).
2. Installs `auto-biblio` at the version pinned by `init` (`@v<version>`).
3. Runs `auto-biblio collect`, which polls every enabled source of `config/sources.yaml`,
   one after the other.
4. Normalizes and deduplicates what the sources return, and stores it in `state/`.
5. Commits and pushes `state/`, even when some sources failed (the run report explains why).

No LLM is involved at this stage: collection is free and deterministic.

### What each source contributes

| Type | What is queried | What is kept |
|---|---|---|
| `arxiv` | arXiv export API, newest submissions first in the configured categories (default cs.CL, cs.LG, cs.CV, cs.AI), pages of 100, 5 s apart, up to `max_results` | papers: title, abstract, authors, categories |
| `hf_papers` | Hugging Face Daily Papers, one request per day covered | papers, the GitHub repository linked to each, **upvotes** |
| `github_search` | GitHub search, one query per topic: repositories created in the last `created_within_days` (30) with more than `min_stars` (50) | repositories, **stars** |
| `github_releases` | releases of the repositories listed under `watch.repos` in `config/profile.yaml` | one item per release, linked to its repository |
| `hackernews` | Hacker News stories above `min_points` (30), via the Algolia API | the content the story links to (an arXiv link becomes the paper), **points** and **comments**; stories without a link become discussions |
| `rss` | any RSS/Atom feed: lab blogs, newsletters, subreddits | posts (or papers and repositories when the link points to arXiv or GitHub) |

Adding an instance of an existing type (a feed, an arXiv category, a topic) only takes a new
entry in `config/sources.yaml`; a new type of source needs a new connector in this package.

### One item per piece of content

Every URL is mapped to a canonical identity, so the same content seen in several places
becomes a single item:

| Identity | Built from |
|---|---|
| `arxiv:2410.12345` | `arxiv.org/abs/…`, `arxiv.org/pdf/…v3`, `huggingface.co/papers/…` |
| `gh:owner/repo` | any `github.com/owner/repo/...` URL (case-insensitive) |
| `gh:owner/repo@tag` | a GitHub release |
| `doi:10.…` | `doi.org/…` |
| `url:<hash>` | any other URL, normalized (https, no `www.`, no tracking parameters, no fragment) |

When two sources report the same identity, the item is merged: each observation is kept as a
*sighting* (source, date, origin URL), and descriptive fields come from the most reliable
source (arXiv > Hugging Face > GitHub > RSS > Hacker News). A paper known only by URL is also
matched to another paper with the same normalized title.

Popularity counters (stars, upvotes, points, comments) are stored separately as dated
*signals*, at most one per item, kind and day: their evolution will reveal rising topics.

### Time windows and failures

- Each source resumes from its **cursor** (last successful run) minus an **overlap** (2 days by
  default, 5 for arXiv, which announces Thursday–Friday submissions on Monday). Its first run
  looks back 7 days. Overlaps and deduplication make a rerun harmless.
- Rate limiting is **retried**: a `429` or `503` answer is retried up to 3 times, after the
  server's `Retry-After` delay (capped at 120 s) or a 10 s / 20 s / 40 s backoff.
- Sources are **isolated**: a source that fails (network error, HTTP error, unexpected payload)
  is reported as `failed`, keeps its cursor and catches up on the next run; the others proceed.
- A paginated source that fails midway (arXiv) keeps the pages it already read: it is
  reported as `partial`, its items are stored, and its cursor does not move, so the next run
  fetches the incomplete window again.
  Unparsable payloads are kept in `state/quarantine/` for diagnosis.
- `auto-biblio collect` exits with 0 when at least one source succeeded (fully or partially), 1 on invalid
  configuration, 2 when every source failed.

### The data repository

```
auto-biblio-data/
├── config/
│   ├── profile.yaml        themes of interest, keywords, watched repositories
│   ├── sources.yaml        sources to poll and their parameters
│   ├── llm.yaml            models, fallback chain and weekly budget of the triage
│   ├── triage.yaml         every decision constant of the triage
│   └── analysis.yaml       notes and theme pages
├── state/
│   ├── items/YYYY-MM.jsonl      deduplicated items, by month first seen, sorted by id
│   ├── signals/YYYY-MM.jsonl    dated stars / upvotes / points / comments
│   ├── cursors.json             last successful run of each source
│   ├── runs/<run>.json          per-source report of each run
│   ├── quarantine/<run>/        payloads a source failed to parse
│   ├── triage/YYYY-Www.json     weekly journal: every candidate, its features, verdict and score
│   ├── feedback/YYYY-MM.jsonl   👍/👎 reactions from the digest
│   └── llm_cache/               cached LLM answers (re-running a week is free)
├── kb/                          knowledge base: notes/, themes/, changelog/ (Markdown)
└── .github/workflows/           daily.yml (collection) and weekly.yml (triage, analysis, digest)
```

Files are written atomically and deterministically (sorted, one JSON object per line), so a
second run on the same day changes nothing in `items/` and `signals/`, and git diffs stay
readable.

### Known limitations

- Reddit and Substack feeds may answer `429`/`403` to cloud IPs such as GitHub runners; those
  sources fail in isolation and are reported.
- The browsable site and the local assistant are the next sub-projects (see the
  [vision](docs/superpowers/specs/2026-10-10-auto-biblio-vision-design.md)).

## Develop

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
make install   # create .venv with all dependency groups + install pre-commit hooks
make check     # lint, typecheck, tests (coverage >= 90 %), strict docs build
uv run python examples/dedup.py   # cross-source deduplication, offline
```

See the [documentation](https://ocoudray.github.io/auto-biblio/) for details.

## Publishing the documentation

The `docs` workflow builds the site with the coverage report and deploys it to GitHub Pages
on every push to `main`. Enable it once in the repository:
**Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Template updates

This project was generated with [Copier](https://copier.readthedocs.io/). To pull in
improvements from the template:

```bash
uvx copier update
```
