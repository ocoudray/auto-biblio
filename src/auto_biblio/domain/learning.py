"""Feedback-driven scoring: labels from the journals, grouped cross-validation, model choice.

Only explicit reactions are reliable labels. Items shown without reaction become weak
negatives after a grace period: they may help training, but never enter an evaluation.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Literal, Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from auto_biblio.domain.feedback import FeedbackEvent
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.scoring import fixed_final_score
from auto_biblio.domain.triage import ScoringReport, TriageRun
from auto_biblio.repo_config.triage import LearningConfig, ScoringWeights

LabelKind = Literal["positive", "negative", "weak_negative"]
FIXED_VERSION = "fixed-v1"


class LabeledExample(BaseModel):
    """One shown item, its features at the time it was shown, and what we know of its value."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    week: str
    inputs: dict[str, float]
    kind: LabelKind

    @property
    def reliable(self) -> bool:
        """Whether the label comes from an explicit reaction."""
        return self.kind != "weak_negative"


def build_examples(
    runs: Sequence[TriageRun], events: Sequence[FeedbackEvent], now: datetime, grace_days: int
) -> list[LabeledExample]:
    """Join the weekly journals with the feedback into labeled examples.

    Args:
        runs: Past triage journals.
        events: Every feedback event.
        now: Current time.
        grace_days: Delay after which a shown item without reaction is a weak negative.

    Returns:
        One example per shown item that has a label, features taken from its latest showing.
    """
    shown: dict[ItemId, tuple[TriageRun, dict[str, float]]] = {}
    for run in sorted(runs, key=lambda r: r.generated_at):
        for item in run.items:
            if item.slot is not None:
                shown[item.item_id] = (run, item.features.model_inputs(item.llm_rel))
    latest: dict[ItemId, FeedbackEvent] = {}
    for event in sorted(events, key=lambda e: e.at):
        latest[event.item_id] = event
    examples: list[LabeledExample] = []
    for item_id, (run, inputs) in sorted(shown.items()):
        event = latest.get(item_id)
        if event is not None:
            kind: LabelKind = "positive" if event.polarity == 1 else "negative"
        elif now - run.generated_at >= timedelta(days=grace_days):
            kind = "weak_negative"
        else:
            continue
        examples.append(LabeledExample(item_id=item_id, week=run.week, inputs=inputs, kind=kind))
    return examples


class ScoringModel(Protocol):
    """Turns the inputs of a candidate into its final score."""

    @property
    def version(self) -> str:
        """Identifies the model in the journal."""
        ...

    def score(self, inputs: Mapping[str, float]) -> float:
        """Score one candidate.

        Args:
            inputs: The candidate's model inputs (`FeatureVector.model_inputs`).

        Returns:
            The final score; higher is better.
        """
        ...


class FixedScoring:
    """The hand-set scoring: weighted prescore blended with the LLM relevance."""

    version = FIXED_VERSION

    def __init__(self, weights: ScoringWeights, llm_weight: float) -> None:
        """Build the scoring.

        Args:
            weights: Prescore weights.
            llm_weight: Share of the LLM relevance in the final score.
        """
        self._weights = weights
        self._llm_weight = llm_weight

    def score(self, inputs: Mapping[str, float]) -> float:
        """Score one candidate; an untriaged one keeps its prescore.

        Args:
            inputs: The candidate's model inputs.

        Returns:
            The final score.
        """
        w = self._weights
        pre = (
            w.relevance * inputs["relevance"]
            + w.popularity * inputs["popularity"]
            + w.multi_source * inputs["multi_source"]
            + w.watched * inputs["watched"]
        )
        if inputs["unverified"]:
            return pre
        return fixed_final_score(pre, inputs["llm_rel"], self._llm_weight)


class LogisticScoring:
    """A logistic regression trained on the feedback: the score is P(👍)."""

    def __init__(self, model: LogisticRegression, names: Sequence[str], version: str) -> None:
        """Wrap a trained model.

        Args:
            model: The fitted regression.
            names: Input names, in the column order the model was trained on.
            version: Identifier written to the journal.
        """
        self._model = model
        self._names = tuple(names)
        self.version = version

    @property
    def coefficients(self) -> dict[str, float]:
        """Coefficient of each input, plus the intercept."""
        coefs = dict(zip(self._names, (float(c) for c in self._model.coef_[0]), strict=True))
        return coefs | {"intercept": float(self._model.intercept_[0])}

    def score(self, inputs: Mapping[str, float]) -> float:
        """Probability that the candidate gets a 👍.

        Args:
            inputs: The candidate's model inputs.

        Returns:
            The predicted probability.
        """
        row = np.array([[inputs[name] for name in self._names]], dtype=np.float64)
        return float(self._model.predict_proba(row)[0, 1])


type Fold = tuple[list[int], list[int]]


def grouped_folds(examples: Sequence[LabeledExample], n_folds: int) -> list[Fold]:
    """Split examples into folds that never share a digest week.

    Test folds keep only reliable labels and must contain both classes; weak negatives
    only ever appear on the training side.

    Args:
        examples: Labeled examples.
        n_folds: Wanted number of folds (capped by the number of weeks).

    Returns:
        (train indices, test indices) per usable fold.
    """
    weeks = [e.week for e in examples]
    n_splits = min(n_folds, len(set(weeks)))
    if n_splits < 2:  # noqa: PLR2004 - a cross-validation needs at least two folds
        return []
    placeholder = np.zeros((len(examples), 1), dtype=np.float64)
    folds: list[Fold] = []
    for train, test in GroupKFold(n_splits=n_splits).split(placeholder, groups=weeks):
        test_reliable = [i for i in map(int, test) if examples[i].reliable]
        classes = {examples[i].kind for i in test_reliable}
        if classes == {"positive", "negative"}:
            folds.append(([int(i) for i in train], test_reliable))
    return folds


def _matrix(
    examples: Sequence[LabeledExample], names: Sequence[str], weak_weight: float
) -> tuple[NDArray[np.float64], NDArray[np.int_], NDArray[np.float64]]:
    x = np.array([[e.inputs[n] for n in names] for e in examples], dtype=np.float64)
    y = np.array([int(e.kind == "positive") for e in examples], dtype=np.int_)
    w = np.array([1.0 if e.reliable else weak_weight for e in examples], dtype=np.float64)
    return x, y, w


def _train(
    examples: Sequence[LabeledExample], names: Sequence[str], weak_weight: float
) -> LogisticRegression | None:
    x, y, w = _matrix(examples, names, weak_weight)
    if len(set(y.tolist())) < 2:  # noqa: PLR2004 - a classifier needs both classes
        return None
    return LogisticRegression(max_iter=1000).fit(x, y, sample_weight=w)


def _auc(examples: Sequence[LabeledExample], scores: Sequence[float]) -> float:
    y = np.array([int(e.kind == "positive") for e in examples], dtype=np.int_)
    return float(roc_auc_score(y, np.asarray(scores, dtype=np.float64)))


def cross_validated_auc(
    examples: Sequence[LabeledExample], cfg: LearningConfig, *, use_weak: bool
) -> float | None:
    """Evaluate the learned scoring by grouped cross-validation on reliable labels.

    Args:
        examples: Labeled examples.
        cfg: The learning configuration.
        use_weak: Whether weak negatives are added to the training folds.

    Returns:
        The mean AUC over the usable folds, or None if no fold is usable.
    """
    names = list(examples[0].inputs) if examples else []
    aucs: list[float] = []
    for train_idx, test_idx in grouped_folds(examples, cfg.cv_folds):
        train = [examples[i] for i in train_idx if use_weak or examples[i].reliable]
        model = _train(train, names, cfg.weak_negative_weight)
        if model is None:
            continue
        scorer = LogisticScoring(model, names, "cv")
        test = [examples[i] for i in test_idx]
        aucs.append(_auc(test, [scorer.score(e.inputs) for e in test]))
    return float(np.mean(aucs)) if aucs else None


def _enough_labels(examples: Sequence[LabeledExample], cfg: LearningConfig) -> bool:
    positives = sum(e.kind == "positive" for e in examples)
    negatives = sum(e.kind == "negative" for e in examples)
    return (
        positives + negatives >= cfg.min_reliable_labels
        and min(positives, negatives) >= cfg.min_per_polarity
    )


def fit_scoring(
    examples: Sequence[LabeledExample], cfg: LearningConfig, fixed: FixedScoring, today: date
) -> tuple[ScoringModel, ScoringReport]:
    """Choose the scoring of this week: learned if it is good enough, fixed otherwise.

    Args:
        examples: Labeled examples.
        cfg: The learning configuration.
        fixed: The hand-set scoring, used as fallback.
        today: Date stamped into the learned model's version.

    Returns:
        The scoring model and the report journaled with the run.
    """
    reliable = sum(e.reliable for e in examples)
    if not _enough_labels(examples, cfg):
        return fixed, ScoringReport(version=fixed.version, reliable_labels=reliable)
    has_weak = any(not e.reliable for e in examples)
    auc_without = cross_validated_auc(examples, cfg, use_weak=False)
    auc_with = cross_validated_auc(examples, cfg, use_weak=True) if has_weak else None
    report = ScoringReport(
        version=fixed.version,
        reliable_labels=reliable,
        auc_without_weak=auc_without,
        auc_with_weak=auc_with,
    )
    use_weak = (auc_with or 0.0) > (auc_without or 0.0)
    best = auc_with if use_weak else auc_without
    if best is None or best < cfg.min_auc:
        return fixed, report
    names = list(examples[0].inputs)
    train = [e for e in examples if use_weak or e.reliable]
    model = _train(train, names, cfg.weak_negative_weight)
    if model is None:  # pragma: no cover - enough labels guarantees both classes
        return fixed, report
    version = f"learned-{today.isoformat()}" + ("-weak" if use_weak else "")
    learned = LogisticScoring(model, names, version)
    return learned, report.model_copy(
        update={"version": version, "coefficients": learned.coefficients}
    )


def evaluate_variants(
    examples: Sequence[LabeledExample], cfg: LearningConfig, fixed: FixedScoring
) -> dict[str, float | None]:
    """Compare the fixed scoring with both learned variants, on reliable labels only.

    Args:
        examples: Labeled examples.
        cfg: The learning configuration.
        fixed: The hand-set scoring.

    Returns:
        AUC of `fixed`, `learned` and `learned_weak` (None when not computable).
    """
    reliable = [e for e in examples if e.reliable]
    classes = {e.kind for e in reliable}
    fixed_auc = (
        _auc(reliable, [fixed.score(e.inputs) for e in reliable])
        if classes == {"positive", "negative"}
        else None
    )
    return {
        "fixed": fixed_auc,
        "learned": cross_validated_auc(examples, cfg, use_weak=False),
        "learned_weak": cross_validated_auc(examples, cfg, use_weak=True),
    }
