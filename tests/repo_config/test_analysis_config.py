import pytest
from pydantic import ValidationError

from auto_biblio.repo_config.analysis import AnalysisConfig


def test_analysis_defaults() -> None:
    cfg = AnalysisConfig()
    assert cfg.deep_count == 4
    assert cfg.max_input_tokens == 30_000
    assert cfg.synthesis_max_input_tokens == 40_000
    assert cfg.relevance_threshold == 3
    assert cfg.max_input_chars == 120_000
    assert cfg.synthesis_max_chars == 160_000


@pytest.mark.parametrize(
    "raw",
    [{"deep_count": -1}, {"relevance_threshold": 6}, {"chars_per_token": 0}, {"deep_cout": 2}],
)
def test_analysis_bounds(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AnalysisConfig.model_validate(raw)
