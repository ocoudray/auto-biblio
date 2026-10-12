# Triage

Every Sunday, `auto-biblio triage` turns the items collected during the week into a short,
ranked and justified selection; `auto-biblio digest` mails it. The full design is in the
[triage spec](superpowers/specs/2026-10-10-triage-design.md). Every constant below is a key of
`config/triage.yaml` (the file `init` writes lists them all with their defaults).

## Pipeline

```
DAILY (no LLM)   collect → signals refresh → feedback ingest → health
WEEKLY           triage: window → embed → features → preselection → context → LLM → selection
                 digest: journal → HTML + text → SMTP
```

`triage` writes `state/triage/<ISO week>.json`, the journal of every candidate (selected or
not) with the features, LLM verdict and score that decided its fate. `digest` only reads that
journal: if the mail fails, re-run `digest` alone.

## Fairness across sources

Sources do not provide the same material: an arXiv paper has a 200-word abstract, a Hacker
News post often only a title, a GitHub repository counts stars while a paper has no signal.
The triage puts every item on comparable scales before combining anything.

| Problem | Answer |
|---|---|
| Longer texts get different similarities | Every item is embedded in the same shape: title + `embed_summary_words` words |
| Families have different similarity scales | Similarity is turned into a **percentile within the item's family** (paper, repo, discussion, feed), over `reference_days` |
| Small families give unstable percentiles | Below `min_family_population` items, the global population is used |
| Signals have different scales | Popularity is the percentile of the signal's velocity **within its kind** (stars vs stars) |
| arXiv has no signal | No signal means `neutral_popularity` (0.5), not 0 |
| arXiv dominates by volume | Each family first gets `family_floor` candidate slots |

## Scores

- **Relevance**: `max over themes (weight × percentile)`, with two anchors per theme: the
  `description` and `label: keywords`.
- **Popularity**: `log1p(growth) / days` over the window, ranked within its signal kind; the
  best kind wins.
- **Prescore**: `weights.relevance × relevance + weights.popularity × popularity +
  weights.multi_source × multi + weights.watched × watched`.
- **Final score (fixed)**: `llm_weight × LLM relevance + (1 − llm_weight) × prescore`; an
  item the LLM did not triage keeps its prescore and is shown as *non vérifié*.

## Selection

1. Exclusion rules (`exclude`, `global_exclude`) drop items before any score, on whole words.
2. Candidates need `relevance ≥ relevance_gate` and must not have been shown before, unless
   they are **revenants**: at least `revenant.min_age_days` old, and either very popular over
   the window or newly seen by another family (an old paper reaching Hacker News), at most
   once every `revenant.cooldown_weeks`.
3. Up to `candidates` items go to the LLM, plus `discovery.slots` **discoveries**: items
   outside the profile with `popularity ≥ discovery.min_popularity`, one per family.
4. The LLM rates each theme from 0 to 5 in batches (titles-only items get a snippet from the
   page, the README or the model card first). An item whose best score is at most `llm_gate`
   is dropped.
5. At most `per_theme_max` items per theme and `selected` in total; a quiet week gives a
   shorter digest, never a padded one.

## LLM, budget and degradation

`config/llm.yaml` lists the models, the chain tried for each role and the weekly budget
(dollars for paid models, tokens for all). A model whose API key is missing is skipped. Calls
to a model are spaced by its `min_interval_s`, to stay under the free tiers' requests-per-minute
caps. A rate limit or an overloaded provider is retried up to `max_retries` times (default 2),
after the delay the provider asks for or an exponential backoff; a daily quota is not retried.
On a persisting quota or availability error, or an invalid answer after one corrective retry,
the next model of the chain takes over; every fallback is written in the journal and the digest footer.
Answers are cached in `state/llm_cache/`, so re-running a week costs nothing and never
exceeds its budget. When the budget runs out, the remaining items are kept unverified.

## Feedback and learning

Each digest line has 👍 / 👎 links that open a prefilled issue in the data repository; the
daily `feedback ingest` records it in `state/feedback/` and closes the issue.

| Label | Source | Use |
|---|---|---|
| positive | 👍 | training and evaluation |
| negative | 👎 | training and evaluation |
| weak negative | shown, no reaction after `learning.weak_negative_grace_days` | training only, weighted by `learning.weak_negative_weight` |

Once `learning.min_reliable_labels` reliable labels exist (with `learning.min_per_polarity`
of each), a logistic regression is trained every week, with and without weak negatives. Both
are evaluated by cross-validation **grouped by digest week, on reliable labels only**; the
better one replaces the fixed scoring if its AUC reaches `learning.min_auc`. The journal and
the digest footer show which scoring ran, its AUC and coefficients.
`auto-biblio eval scoring` compares the three variants at any time.
