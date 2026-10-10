# Auto Biblio Recap

[![CI](https://github.com/ocoudray/auto-biblio/actions/workflows/ci.yml/badge.svg)](https://github.com/ocoudray/auto-biblio/actions/workflows/ci.yml)
[![Coverage](https://ocoudray.github.io/auto-biblio/badges/coverage.svg)](https://ocoudray.github.io/auto-biblio/coverage-report/)
[![Docs](https://img.shields.io/badge/docs-zensical-blue)](https://ocoudray.github.io/auto-biblio/)

An automated watch on AI research and engineering. It collects new papers, repositories,
releases, blog posts and discussions (arXiv, Hugging Face Daily Papers, GitHub, Hacker News,
RSS), deduplicates them across sources and stores them in a separate data repository. Triage,
analysis and the weekly digest come in the next sub-projects (see the
[vision](docs/superpowers/specs/2026-10-10-auto-biblio-vision-design.md)).

## Quickstart

```bash
uv tool install git+https://github.com/ocoudray/auto-biblio
auto-biblio init ~/auto-biblio-data      # config + daily GitHub Actions workflow
auto-biblio collect --data-dir ~/auto-biblio-data
```

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
