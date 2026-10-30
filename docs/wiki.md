# Knowledge wiki

Next to the weekly watch, the data repository holds a **wiki of established knowledge**: one
page per notion (`llm/attention`, `llm/transformer`…), teaching-oriented, illustrated and
validated by its owner, and linked to the notes of the watch that move it forward. The full
design is in the [wiki spec](superpowers/specs/2026-10-17-wiki-design.md).

The pipeline never writes a wiki page. Pages are drafted on demand with Claude Code, through
three skills installed in the data repository, and each page is validated by merging its pull
request.

## Layout

```
wiki/
├── GUIDE.md                 living style guide, read by the skills
└── llm/
    ├── index.md             domain title, reading order, introduction
    ├── attention.md         one notion
    ├── img/                 figures, and the scripts that draw them
    └── code/                notebooks published with the site, and their sources
```

- A notion's identifier is its path without extension: `llm/attention`
  (`^[a-z0-9-]+/[a-z0-9-]+$`).
- A domain `index.md` has a front-matter `title` and `order` (the notions in reading order),
  then a free introduction. A notion listed in `order` without a file is *planned*.
- The wiki is organised by domain, independently of the watch themes of
  `config/profile.yaml`.

### A notion page

```markdown
---
title: Mécanisme d'attention
aliases: [attention, self-attention, scaled dot-product attention]
prerequisites: [llm/embeddings]
related: [llm/multi-head-attention, llm/transformer]
themes: [agentic, rag]
updated_at: 2026-10-20
---

# Mécanisme d'attention

Summary, 3 to 5 lines.

## Intuition
## Formalisation
## Exemple pas à pas
## Pièges et idées reçues
## Variantes et évolutions
## Références fondatrices
## Mes notes
```

The summary and `## Références fondatrices` are required; the other sections are left out
when they do not apply. `## Mes notes` belongs to the owner: no skill rewrites it without an
explicit go-ahead. `aliases` are the other names the notes use for the notion; they let
`wiki link` recognise it.

### Illustrations

| Kind | Tool | File |
|---|---|---|
| flows, steps, sequences | a ` ```mermaid ` block in the page | — |
| architecture diagrams | hand-drawn SVG | `img/<name>.svg` |
| computed plots | Python script (matplotlib) | `img/<name>.py` writes `img/<name>.svg` |

Every image has an alt text and, on the next line, an italic caption that states where it
comes from: *Figure originale* or *Source : author, link, licence*. A third-party figure is
reused only under an open licence; otherwise the page draws an original diagram "d'après" the
source, or links to it. Equations are LaTeX (`$…$`, `$$…$$`) and render with MathJax.

### Notebooks

A page offers a notebook to download with a relative link: `[notebook](code/<name>.ipynb)`.
The site publishes `wiki/<domain>/code/*.ipynb` and nothing else from `code/` (`.py`, `.json`,
`.pt`...), and `wiki check` reports a link to a notebook that does not exist. Everything
published is public to whoever can open the site: keep secrets and private data out of the
notebook, its outputs included.

## The review loop

```
/wiki-plan llm     ──► plan PR ──► review ──► merge
/wiki-rediger      ──► page PR ──► review ──► /wiki-reprendre <PR> ──► … ──► merge
                                                  └─► rules proposed for GUIDE.md
```

Run the skills with Claude Code from the data repository:

| Skill | What it does |
|---|---|
| `/wiki-plan <domain>` | Proposes `wiki/<domain>/index.md`: notions, prerequisites, reading order, from reference courses and `state/wiki/candidates.json`. Opens a PR. |
| `/wiki-rediger [notion]` | Without argument, takes the first planned notion whose prerequisites all have a page. Reads the guide, the prerequisites and the linked notes, searches reference sources, writes the page and its figures, runs `wiki check` and the site build, and opens a PR listing its sources and what to check first. |
| `/wiki-reprendre <PR>` | Reads the review comments, applies them, answers every thread, and proposes the generalisable rules for `wiki/GUIDE.md` in a separate commit that you keep or drop before merging. |

Review comments go on the GitHub pull request. The rules they produce accumulate in the
*Règles issues des relectures* section of `wiki/GUIDE.md`, so the next pages follow them;
the skills themselves only change with auto-biblio versions.

## `auto-biblio wiki check`

```bash
auto-biblio wiki check
```

Lists every problem with its file, and exits with code 1 when there is one:

- front-matter of each notion and each `index.md`;
- `prerequisites`, `related` and `order` name existing or planned notions, and prerequisites
  have no cycle;
- `themes` name themes of the profile;
- summary and `## Références fondatrices` present;
- images exist and have a caption with their provenance; relative links are not broken;
- every notion is in the `order` of its domain.

Without `wiki/`, it prints `no wiki/ directory` and succeeds. The `wiki-check.yml` workflow of
the data repository runs it, then the site build, on every pull request that touches `wiki/`.

## `auto-biblio wiki link`

The weekly workflow runs `auto-biblio wiki link` after `analyze`. It asks the LLM (role
`wiki_link`, chain `[flash-lite, flash-lite-3.1, gemma]`, batches of `batch_size` notes)
which notions of the wiki each note is about, and which concepts it uses that have no page
yet (at most 3 per note).

- `state/wiki/links.json`: the notions of each note, and the catalogue signature used.
- `state/wiki/candidates.json`: the concepts without a page, with their notes and dates.

Only new notes, and every note once the catalogue (ids, titles, aliases) changes, are sent
again. A concept that matches a title or an alias becomes a link, not a candidate. The step
shares the weekly token budget with the triage and the analysis; a failed batch is left for
next week and never blocks the site or the digest. Without `wiki/`, it does nothing.

## On the site

The [site](site.md) has a **Wiki** section: one menu per domain (its introduction, then the
notions in reading order) and a **Notions à couvrir** page listing the candidates, most cited
first. A notion page shows its *Prérequis* under the title and, before *Mes notes*, the
*Nouveautés suivies*: the linked notes, newest first. Each note shows a *Notions* line linking
to its notions. Equations, Mermaid diagrams and figures are rendered, and notebooks can be
downloaded.
