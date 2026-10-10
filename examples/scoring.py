"""Show how candidates from different sources are ranked fairly, with the default settings.

Run with `uv run python examples/scoring.py` (no network, no model, no LLM).
"""

from auto_biblio.domain.features import FeatureVector, SourceFamily
from auto_biblio.domain.scoring import prescore
from auto_biblio.domain.selection import pick_discoveries, preselect
from auto_biblio.repo_config.triage import TriageConfig

CONFIG = TriageConfig()


def candidate(
    item_id: str, family: SourceFamily, relevance: float, popularity: float
) -> FeatureVector:
    """Build the features of an item; relevance and popularity are percentiles."""
    return FeatureVector.model_validate(
        {
            "item_id": item_id,
            "family": family,
            "context_level": "abstract" if family == "paper" else "title_only",
            "theme_similarity": {},
            "theme_percentile": {"agentic": relevance},
            "relevance": relevance,
            "popularity": popularity,
            "source_count": 1,
            "watched": False,
            "revenant": False,
            "age_days": 2.0,
        }
    )


def main() -> None:
    """Rank a mixed week and print the candidates and discoveries."""
    week = [
        *(candidate(f"arxiv:2410.{i:05}", "paper", 0.80 + i / 100, 0.5) for i in range(12)),
        candidate("url:hn-agent-runtime", "discussion", 0.95, 0.90),
        candidate("gh:acme/agent-kit", "repo", 0.78, 0.70),
        candidate("gh:acme/game-engine", "repo", 0.10, 0.99),
    ]
    prescores = {f.item_id: prescore(f, CONFIG.weights) for f in week}
    chosen = preselect(week, prescores, frozenset(), CONFIG)
    rest = [f for f in week if f.item_id not in chosen]
    print("Candidates sent to the LLM (best prescore first):")
    for item_id in chosen:
        print(f"  {prescores[item_id]:.3f}  {item_id}")
    print("Discoveries (popular, outside the profile):")
    for item_id in pick_discoveries(rest, frozenset(), CONFIG):
        print(f"  {item_id}")


if __name__ == "__main__":
    main()
