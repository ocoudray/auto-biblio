from pathlib import Path

import pytest

from auto_biblio.domain.errors import ConfigError
from auto_biblio.repo_config.loader import load_repo_config

PROFILE = """
themes:
  - id: agentic
    label: Agentic
    description: Agents.
    watch: {repos: [pydantic/pydantic-ai]}
"""
SOURCES = """
sources:
  - {name: arxiv, type: arxiv, categories: [cs.CL]}
  - {name: hn, type: hackernews}
  - {name: github-rising, type: github_search, topics: [llm], min_stars: %s}
"""


def write_repo(root: Path, *, profile: str = PROFILE, min_stars: str = "50") -> Path:
    config = root / "config"
    config.mkdir()
    (config / "profile.yaml").write_text(profile)
    (config / "sources.yaml").write_text(SOURCES % min_stars)
    return root


def test_load_valid_config(tmp_path: Path) -> None:
    config = load_repo_config(write_repo(tmp_path))
    assert config.profile.watched_repos() == ("pydantic/pydantic-ai",)
    assert len(config.sources.sources) == 3


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"config/profile\.yaml"):
        load_repo_config(tmp_path)


def test_invalid_yaml_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"config/profile\.yaml"):
        load_repo_config(write_repo(tmp_path, profile="themes: [unclosed"))


def test_invalid_field_message(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_repo_config(write_repo(tmp_path, min_stars='"beaucoup"'))
    assert str(excinfo.value).startswith("config/sources.yaml: sources.2.github_search.min_stars:")


LLM = """
models:
  flash: {id: "test:flash", input_usd_per_mtok: 0, output_usd_per_mtok: 0, batch_size: 20}
chains: {triage: [flash]}
weekly_budget: {usd: 0.5, tokens: 300000}
"""


def test_loader_reads_llm_and_triage(tmp_path: Path) -> None:
    root = write_repo(tmp_path)
    (root / "config" / "llm.yaml").write_text(LLM)
    (root / "config" / "triage.yaml").write_text("selected: 12\n")
    config = load_repo_config(root)
    assert config.triage.selected == 12
    assert config.require_llm().chain("triage")[0].id == "test:flash"


def test_loader_triage_optional(tmp_path: Path) -> None:
    config = load_repo_config(write_repo(tmp_path))
    assert config.triage.selected == 18


def test_loader_llm_required_only_when_used(tmp_path: Path) -> None:
    config = load_repo_config(write_repo(tmp_path))
    with pytest.raises(ConfigError, match=r"config/llm\.yaml"):
        config.require_llm()


def test_loader_invalid_triage(tmp_path: Path) -> None:
    root = write_repo(tmp_path)
    (root / "config" / "triage.yaml").write_text("relevance_gate: 2\n")
    with pytest.raises(ConfigError, match=r"config/triage\.yaml: relevance_gate"):
        load_repo_config(root)


def test_empty_triage_file_means_defaults(tmp_path: Path) -> None:
    root = write_repo(tmp_path)
    (root / "config" / "triage.yaml").write_text("# nothing\n")
    assert load_repo_config(root).triage.candidates == 50


def test_loader_reads_analysis(tmp_path: Path) -> None:
    root = write_repo(tmp_path)
    assert load_repo_config(root).analysis.deep_count == 4
    (root / "config" / "analysis.yaml").write_text("deep_count: 2\n")
    assert load_repo_config(root).analysis.deep_count == 2
    (root / "config" / "analysis.yaml").write_text("")
    assert load_repo_config(root).analysis.deep_count == 4
