# Auto Biblio Recap

[![CI](https://github.com/ocoudray/auto-biblio/actions/workflows/ci.yml/badge.svg)](https://github.com/ocoudray/auto-biblio/actions/workflows/ci.yml)
[![Coverage](https://ocoudray.github.io/auto-biblio/badges/coverage.svg)](https://ocoudray.github.io/auto-biblio/coverage-report/)
[![Docs](https://img.shields.io/badge/docs-zensical-blue)](https://ocoudray.github.io/auto-biblio/)

Routine to fetch automatically new research and development on AI, and give a recap of the most relevant advances

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
make install   # create .venv with all dependency groups + install pre-commit hooks
make check     # lint, typecheck, tests (coverage >= 90 %), strict docs build
```

## Try it

Each enabled use case ships a minimal, runnable example:

```bash
uv run python examples/quickstart.py   # library: call the core logic
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
