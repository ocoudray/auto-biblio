"""Weekly triage: from the collected items to a short, ranked and justified selection."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import BudgetExhaustedError, ChainExhaustedError, EmbeddingError
from auto_biblio.domain.features import FeatureVector, ThemeId, context_level, embedding_text
from auto_biblio.domain.featurize import (
    FeatureInputs,
    ProfileView,
    build_features,
    keyword_similarities,
)
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.learning import FixedScoring, ScoringModel, build_examples, fit_scoring
from auto_biblio.domain.models import Clock, Item
from auto_biblio.domain.scoring import ThemeAnchors, llm_relevance, prescore, theme_similarities
from auto_biblio.domain.selection import final_selection, is_excluded, pick_discoveries, preselect
from auto_biblio.domain.triage import (
    LLMUsage,
    ScoredItem,
    ScoringReport,
    TriageRun,
    TriageVerdict,
)
from auto_biblio.embeddings import Embedder
from auto_biblio.llm import StructuredLLM
from auto_biblio.llm.chain import FallbackHook
from auto_biblio.llm.prompts.triage_v1 import make_batches, to_inputs, triage_task
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.store.feedback import FeedbackStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.signals import SignalStore
from auto_biblio.store.triage import TriageStore

logger = logging.getLogger(__name__)

type LLMFactory = Callable[[BudgetLedger, FallbackHook], StructuredLLM]


class ContextSource(Protocol):
    """Fetches snippets for items without summary (see `ContextFetcher`)."""

    def fetch_many(self, items: Sequence[Item]) -> dict[ItemId, str]:
        """Fetch snippets, skipping failures."""
        ...


def iso_week(moment: datetime) -> str:
    """Name the ISO week of a date.

    Args:
        moment: Any date.

    Returns:
        `YYYY-Www`.
    """
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass(frozen=True)
class _Pools:
    population: list[Item]
    pool: list[Item]


@dataclass
class _LLMOutcome:
    verdicts: dict[ItemId, TriageVerdict]
    usage: list[LLMUsage]


class TriageStage:
    """Runs the weekly triage and writes its journal."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        config: RepoConfig,
        items: ItemStore,
        signals: SignalStore,
        feedback: FeedbackStore,
        store: TriageStore,
        *,
        embedder: Embedder,
        llm_factory: LLMFactory,
        context: ContextSource,
        clock: Clock,
    ) -> None:
        """Build the stage.

        Args:
            config: The data repository configuration (`llm.yaml` required).
            items: Collected items.
            signals: Popularity signals.
            feedback: Feedback events.
            store: Weekly journals (read and written).
            embedder: Local embedder.
            llm_factory: Builds the LLM of the run from its budget ledger and fallback hook.
            context: Snippets for items without summary.
            clock: Current time provider.
        """
        self._config = config
        self._llm_config = config.require_llm()
        self._llm_config.require("triage")
        self._cfg = config.triage
        self._view = ProfileView.of(config.profile)
        self._items = items
        self._signals = signals
        self._feedback = feedback
        self._store = store
        self._embedder = embedder
        self._llm_factory = llm_factory
        self._context = context
        self._clock = clock

    def run(self, week: str | None = None) -> TriageRun:
        """Triage the items of a week and write the journal.

        Args:
            week: ISO week to triage (default: the current one). Re-running a week
                replaces its journal and reuses its budget and LLM cache.

        Returns:
            The journal.
        """
        now = self._clock()
        week = week or iso_week(now)
        past = [run for run in self._store.all() if run.week != week]
        degradations: list[str] = []
        pools = self._pools(now, past)
        features = self._features(pools, past, now, degradations)
        candidates, discoveries = self._preselect(features, past)
        chosen = [*candidates, *discoveries]
        snippets = self._context.fetch_many(
            [item for item in map(self._item, chosen) if not item.summary]
        )
        features = _with_context_levels(features, snippets, self._item)
        items = [self._item(i) for i in chosen]
        texts = {i.id: i.summary or snippets.get(i.id) for i in items}
        outcome = self._triage(items, texts, features, week, degradations)
        model, report = self._scoring(past, now)
        scored = self._score(chosen, set(discoveries), features, outcome, model)
        run = TriageRun(
            week=week,
            run_id=f"{now:%Y%m%dT%H%M%SZ}-triage",
            generated_at=now,
            scoring=report,
            items=final_selection(scored, self._view.weights, self._cfg),
            usage=tuple(outcome.usage),
            degradations=tuple(degradations),
        )
        self._store.write(run)
        logger.info("triage %s: %d candidates, %d selected", week, len(chosen), len(run.selected()))
        return run

    def _item(self, item_id: ItemId) -> Item:
        item = self._items.get(item_id)
        if item is None:  # pragma: no cover - ids come from the same store
            msg = f"unknown item {item_id}"
            raise KeyError(msg)
        return item

    def _pools(self, now: datetime, past: Sequence[TriageRun]) -> _Pools:
        reference_start = now - timedelta(days=self._cfg.reference_days)
        window_start = now - timedelta(days=self._cfg.window_days)
        kept = [i for i in self._items.all() if not is_excluded(i, self._view.exclusions)]
        population = [i for i in kept if i.first_seen >= reference_start]
        pool = [i for i in kept if i.first_seen >= window_start or self._active(i, window_start)]
        logger.debug(
            "%d items in population, %d in pool (%d runs)", len(population), len(pool), len(past)
        )
        return _Pools(population=population, pool=pool)

    def _active(self, item: Item, since: datetime) -> bool:
        return any(s.seen_at >= since for s in item.sightings) or any(
            s.observed_at >= since for s in self._signals.history(item.id)
        )

    def _features(
        self, pools: _Pools, past: Sequence[TriageRun], now: datetime, degradations: list[str]
    ) -> dict[ItemId, FeatureVector]:
        every = {i.id: i for i in (*pools.population, *pools.pool)}
        last_shown: dict[ItemId, datetime] = {}
        for run in sorted(past, key=lambda r: r.generated_at):
            last_shown.update(dict.fromkeys(run.shown_ids(), run.generated_at))
        inputs = FeatureInputs(
            population=pools.population,
            pool=pools.pool,
            similarities=self._similarities(list(every.values()), degradations),
            histories={i: self._signals.history(i) for i in every},
            last_shown=last_shown,
            window_start=now - timedelta(days=self._cfg.window_days),
            now=now,
        )
        return build_features(inputs, self._view, self._cfg)

    def _similarities(
        self, items: Sequence[Item], degradations: list[str]
    ) -> dict[ItemId, dict[ThemeId, float]]:
        themes = self._config.profile.themes
        anchor_texts = [
            text for t in themes for text in (t.description, f"{t.label}: {', '.join(t.keywords)}")
        ]
        texts = [embedding_text(i, self._cfg.embed_summary_words) for i in items]
        try:
            vectors = self._embedder.embed([*anchor_texts, *texts])
        except EmbeddingError as exc:
            logger.warning("embeddings unavailable, falling back to keywords: %s", exc)
            degradations.append(f"embedding fallback: {exc}")
            return {i.id: keyword_similarities(i, self._view) for i in items}
        anchors = [
            ThemeAnchors(
                theme=ThemeId(t.id), weight=t.weight, vectors=tuple(vectors[2 * k : 2 * k + 2])
            )
            for k, t in enumerate(themes)
        ]
        item_vectors = vectors[len(anchor_texts) :]
        return {
            i.id: theme_similarities(v, anchors) for i, v in zip(items, item_vectors, strict=True)
        }

    def _preselect(
        self, features: dict[ItemId, FeatureVector], past: Sequence[TriageRun]
    ) -> tuple[tuple[ItemId, ...], tuple[ItemId, ...]]:
        shown = frozenset(i for run in past for i in run.shown_ids())
        vectors = list(features.values())
        prescores = {f.item_id: prescore(f, self._cfg.weights) for f in vectors}
        candidates = preselect(vectors, prescores, shown, self._cfg)
        rest = [f for f in vectors if f.item_id not in set(candidates)]
        return candidates, pick_discoveries(rest, shown, self._cfg)

    def _triage(
        self,
        items: Sequence[Item],
        texts: dict[ItemId, str | None],
        features: dict[ItemId, FeatureVector],
        week: str,
        degradations: list[str],
    ) -> _LLMOutcome:
        previous = self._store.read(week)
        spent_usd, spent_tokens = previous.usage_totals() if previous else (0.0, 0)
        ledger = BudgetLedger(self._llm_config.weekly_budget, spent_usd, spent_tokens)

        def on_fallback(role: str, model_id: str, reason: str) -> None:
            degradations.append(f"fallback {role}: {model_id} ({reason})")

        llm = self._llm_factory(ledger, on_fallback)
        inputs = to_inputs([(i, texts[i.id], features[i.id].context_level) for i in items])
        ref_to_id = {inp.ref: item.id for inp, item in zip(inputs, items, strict=True)}
        size = self._llm_config.chain("triage")[0].batch_size
        outcome = _LLMOutcome(verdicts={}, usage=[])
        for batch in make_batches(inputs, size):
            try:
                result = llm.run(triage_task(batch, self._config.profile.themes))
            except BudgetExhaustedError as exc:
                degradations.append(f"budget exhausted ({exc}): remaining batches not triaged")
                break
            except ChainExhaustedError as exc:
                degradations.append(f"batch not triaged: {exc}")
                continue
            outcome.usage.append(result.usage)
            outcome.verdicts.update({ref_to_id[v.ref]: v for v in result.output.verdicts})
        return outcome

    def _scoring(
        self, past: Sequence[TriageRun], now: datetime
    ) -> tuple[ScoringModel, ScoringReport]:
        examples = build_examples(
            past, self._feedback.all(), now, self._cfg.learning.weak_negative_grace_days
        )
        fixed = FixedScoring(self._cfg.weights, self._cfg.llm_weight)
        return fit_scoring(examples, self._cfg.learning, fixed, now.date())

    def _score(
        self,
        chosen: Sequence[ItemId],
        discoveries: set[ItemId],
        features: dict[ItemId, FeatureVector],
        outcome: _LLMOutcome,
        model: ScoringModel,
    ) -> list[ScoredItem]:
        scored: list[ScoredItem] = []
        for item_id in chosen:
            f = features[item_id]
            verdict = outcome.verdicts.get(item_id)
            llm_rel = llm_relevance(verdict, self._view.weights) if verdict else None
            scored.append(
                ScoredItem(
                    item_id=item_id,
                    features=f,
                    prescore=prescore(f, self._cfg.weights),
                    verdict=verdict,
                    llm_rel=llm_rel,
                    final_score=model.score(f.model_inputs(llm_rel)),
                    discovery=item_id in discoveries,
                )
            )
        return scored


def _with_context_levels(
    features: dict[ItemId, FeatureVector],
    snippets: dict[ItemId, str],
    lookup: Callable[[ItemId], Item],
) -> dict[ItemId, FeatureVector]:
    updated = dict(features)
    for item_id, snippet in snippets.items():
        level = context_level(lookup(item_id), snippet)
        updated[item_id] = features[item_id].model_copy(update={"context_level": level})
    return updated
