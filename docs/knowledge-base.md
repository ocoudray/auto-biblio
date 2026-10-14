# Knowledge base

Every Sunday, after the triage, `auto-biblio analyze` turns the selected items into a living
knowledge base in the data repository (`kb/`), and `auto-biblio digest` links to it. The full
design is in the [analysis spec](superpowers/specs/2026-10-10-analyse-kb-design.md); every
constant below is a key of `config/analysis.yaml`.

## Layout

```
kb/
├── notes/papers/<slug>.md    one note per paper
├── notes/tools/<slug>.md     one note per repository (its releases update it)
├── notes/posts/<slug>.md     blog posts, newsletters, discussions
├── themes/<theme-id>.md      state of the art of each theme
└── changelog/YYYY-Www.md     what changed each week
```

Notes and pages are Markdown with a YAML front-matter. They are written from structured LLM
output through fixed templates, so their shape is stable and the pipeline can read them back.

## Notes

- The `deep_count` best items of the digest get a **deep analysis** from their full text:
  problem, method, results, limitations, positioning, practical takeaways, links to explore,
  and a one-sentence verdict.
- The other items, discoveries included, get a **short note** from their abstract: summary,
  contribution and why it matters for your themes.
- A note is written once. It is rewritten only to deepen it, when the item comes back among
  the best, or when its prompt version changes. A deep note is never downgraded.
- **`## Mes notes`**: write your own notes under this heading. The pipeline copies it
  verbatim on every rewrite.
- `source_text` tells what the model read: `full_text`, `abstract`, `snippet` or `title`.

### Full text

| Item | Source |
|---|---|
| arXiv paper | the HTML rendering on arxiv.org, else the PDF |
| GitHub repository or release | the README and the latest release notes |
| Blog post, newsletter | the main content of the page |

References, acknowledgements and appendices are cut, and the text is capped at
`max_input_tokens`. When no full text can be obtained, the note is a short one written from
the abstract, and the changelog says why. Full texts are cached in `.cache/fulltext/` (not
committed).

## Theme pages

One theme page is rewritten each week: the least recently updated theme among those that
received new notes. The page gives an overview, key concepts, dominant approaches, reference
tools linked to their notes, open questions and further reading.

**No link is ever lost silently**: every link of the previous page must be kept, or listed
with a reason in the changelog. A rewrite that drops a link without a reason is rejected,
and after a second failure the previous page is kept.

## Changelog and digest

`kb/changelog/YYYY-Www.md` lists the notes created, deepened or rewritten, the theme page
rewritten, and the links added or removed. The digest shows the same changes under
*Évolutions de la base*, links each item to its note, and shows the verdict of deep analyses.
With a [site](site.md), these links open the note on the site instead of GitHub.

## Reliability

- `analyze` shares the weekly LLM budget with the triage. It writes the short notes first,
  then the deep analyses, then the theme page, so that a budget shortage drops the most
  expensive steps first.
- If `analyze` fails, the digest is still sent, without the new notes.
- Re-running `analyze` for a week changes nothing: cached answers are reused and the theme
  page of the week is not rewritten twice.
- Revert any change with `git revert` in the data repository.

## Settings (`config/analysis.yaml`)

| Key | Default | Meaning |
|---|---|---|
| `deep_count` | 4 | items analysed from their full text each week |
| `max_input_tokens` | 30000 | size cap of a full text |
| `synthesis_max_input_tokens` | 40000 | size cap of the notes sent to write a theme page |
| `relevance_threshold` | 3 | minimum LLM relevance (0-5) to attach a note to a theme |
| `chars_per_token` | 4 | conversion from tokens to characters |
