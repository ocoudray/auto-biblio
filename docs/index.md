# Auto Biblio Recap

An automated watch on AI research and engineering: it collects new papers, repositories,
releases, blog posts and community discussions, deduplicates them across sources, triages
them against an interest profile into a weekly digest, and (in upcoming sub-projects)
maintains a living knowledge base.

**Status:** sub-projects 1 and 2 are implemented:

- *foundation and collection*: a daily, LLM-free collection from arXiv, Hugging Face Daily
  Papers, GitHub, Hacker News and RSS feeds into a separate data repository;
- *triage*: a weekly ranking with local embeddings, fair percentiles across sources, a cheap
  LLM within a budget, and a raw digest by mail whose 👍/👎 feedback trains the scoring.

- [Getting started](getting-started.md): install, create a data repository, collect.
- [Triage](triage.md): how items are ranked, and every setting of `triage.yaml`.
- [Design](superpowers/specs/2026-10-10-auto-biblio-vision-design.md): the overall vision
  the [collection spec](superpowers/specs/2026-10-10-socle-collecte-design.md) and the
  [triage spec](superpowers/specs/2026-10-10-triage-design.md).
- [API reference](reference/index.md): generated from the docstrings.
- [Coverage](coverage.md): latest test coverage report.
