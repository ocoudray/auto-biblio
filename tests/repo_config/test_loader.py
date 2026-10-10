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
