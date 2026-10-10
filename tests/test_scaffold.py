from importlib.resources import files
from pathlib import Path

import pytest

from auto_biblio.repo_config.loader import load_repo_config
from auto_biblio.repo_config.triage import TriageConfig
from auto_biblio.scaffold import ScaffoldExistsError, scaffold_data_repo

EXPECTED = [
    ".github/workflows/daily.yml",
    ".github/workflows/weekly.yml",
    ".gitignore",
    "config/llm.yaml",
    "config/profile.yaml",
    "config/sources.yaml",
    "config/triage.yaml",
    "state/.gitkeep",
]


def test_scaffold_creates_files(tmp_path: Path) -> None:
    created = scaffold_data_repo(tmp_path, "1.2.3")
    assert sorted(p.relative_to(tmp_path).as_posix() for p in created) == EXPECTED
    assert all(p.is_file() for p in created)


def test_scaffolded_config_is_valid(tmp_path: Path) -> None:
    scaffold_data_repo(tmp_path, "1.2.3")
    config = load_repo_config(tmp_path)
    assert [t.id for t in config.profile.themes] == [
        "agentic",
        "rag-scale",
        "tabular-fm",
        "llm-arch",
        "ai-dev-practices",
        "vlm-vs-ocr",
        "doc-dataification",
    ]
    types = {s.type for s in config.sources.sources}
    assert types == {"arxiv", "hf_papers", "github_search", "github_releases", "hackernews", "rss"}
    assert "pydantic/pydantic-ai" in config.profile.watched_repos()


def test_workflow_pins_version(tmp_path: Path) -> None:
    scaffold_data_repo(tmp_path, "1.2.3")
    workflow = (tmp_path / ".github" / "workflows" / "daily.yml").read_text()
    assert "auto-biblio@v1.2.3" in workflow
    assert 'cron: "0 5 * * *"' in workflow
    assert "${{ secrets.GITHUB_TOKEN }}" in workflow


def test_refuses_to_overwrite(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "profile.yaml").write_text("mine")
    with pytest.raises(ScaffoldExistsError) as excinfo:
        scaffold_data_repo(tmp_path, "1.2.3")
    assert excinfo.value.paths == (tmp_path / "config" / "profile.yaml",)
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["profile.yaml"]
    assert (tmp_path / "config" / "profile.yaml").read_text() == "mine"


def test_templates_ship_with_package() -> None:
    template = files("auto_biblio.scaffold_templates").joinpath("sources.yaml")
    assert "arxiv" in template.read_text(encoding="utf-8")


def test_workflow_commits_state_even_when_collect_fails(tmp_path: Path) -> None:
    scaffold_data_repo(tmp_path, "1.2.3")
    workflow = (tmp_path / ".github" / "workflows" / "daily.yml").read_text()
    commit_step = workflow[workflow.index("- name: Commit state") :]
    assert "if: ${{ !cancelled() }}" in commit_step


def test_gitignore_excludes_interrupted_writes(tmp_path: Path) -> None:
    scaffold_data_repo(tmp_path, "1.2.3")
    assert "*.tmp" in (tmp_path / ".gitignore").read_text().splitlines()


def test_scaffolded_triage_config(tmp_path: Path) -> None:
    scaffold_data_repo(tmp_path, "1.2.3")
    config = load_repo_config(tmp_path)
    assert config.triage == TriageConfig()  # the template spells out the defaults
    llm = config.require_llm()
    assert [s.id for s in llm.chain("triage")] == [
        "google:gemini-3.5-flash-lite",
        "anthropic:claude-haiku-5-5",
    ]


def test_workflows_pin_the_version(tmp_path: Path) -> None:
    scaffold_data_repo(tmp_path, "1.2.3")
    daily = (tmp_path / ".github/workflows/daily.yml").read_text()
    weekly = (tmp_path / ".github/workflows/weekly.yml").read_text()
    for workflow in (daily, weekly):
        assert "auto-biblio@v1.2.3" in workflow
        assert "${{ secrets.GITHUB_TOKEN }}" in workflow
    assert "auto-biblio signals refresh" in daily
    assert "auto-biblio feedback ingest" in daily
    assert "auto-biblio health" in daily
    assert "issues: write" in daily
    assert "auto-biblio triage" in weekly
    assert '${WEEK:+--week "$WEEK"}' in weekly
