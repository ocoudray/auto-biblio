from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from auto_biblio.repo_config.analysis import AnalysisConfig
from auto_biblio.repo_config.loader import load_repo_config
from auto_biblio.repo_config.triage import TriageConfig
from auto_biblio.scaffold import ScaffoldExistsError, scaffold_data_repo

EXPECTED = [
    ".github/workflows/daily.yml",
    ".github/workflows/weekly.yml",
    ".gitignore",
    "config/analysis.yaml",
    "config/llm.yaml",
    "config/profile.yaml",
    "config/sources.yaml",
    "config/triage.yaml",
    "kb/.gitkeep",
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
    assert config.analysis == AnalysisConfig()
    llm = config.require_llm()
    assert [s.id for s in llm.chain("triage")] == [
        "google:gemini-3.5-flash-lite",
        "google:gemini-3.1-flash-lite",
        "google:gemma-4-31b-it",
    ]
    llm.require("triage", "short_note", "deep_analysis", "synthesis")
    assert llm.chain("deep_analysis")[0].id == "google:gemini-3.8-flash"
    # Every model of the large-prompt chains can take the largest prompt the analysis sends.
    assert all(s.fits(config.analysis.max_input_chars) for s in llm.chain("deep_analysis"))
    assert all(s.fits(config.analysis.synthesis_max_chars) for s in llm.chain("synthesis"))


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
    assert "auto-biblio analyze" in weekly
    assert "continue-on-error: true" in weekly
    assert "git add state kb" in weekly
    assert '${WEEK:+--week "$WEEK"}' in weekly


def weekly_steps(tmp_path: Path) -> dict[str, dict[str, object]]:
    scaffold_data_repo(tmp_path, "1.2.3")
    raw = yaml.safe_load((tmp_path / ".github/workflows/weekly.yml").read_text())
    steps: list[dict[str, object]] = raw["jobs"]["triage"]["steps"]
    return {str(step["name"]): step for step in steps if "name" in step}


def test_weekly_builds_and_deploys_the_site_before_the_digest(tmp_path: Path) -> None:
    steps = weekly_steps(tmp_path)
    names = list(steps)
    assert names[names.index("Analyze") :] == [
        "Analyze",
        "Site build",
        "Site deploy",
        "Digest",
        "Keep the dry-run digest",
        "Keep the dry-run site",
        "Commit state",
        "Report a site failure",
    ]
    assert steps["Site build"]["continue-on-error"] is True
    assert steps["Site build"]["run"] == "auto-biblio site build --out site"
    deploy = steps["Site deploy"]
    assert deploy["continue-on-error"] is True
    assert deploy["uses"] == "cloudflare/wrangler-action@v3"
    assert "inputs.dry_run" in str(deploy["if"])
    assert "pages deploy site" in str(deploy["with"])
    assert "${{ secrets.CLOUDFLARE_API_TOKEN }}" in str(deploy["with"])
    assert "inputs.dry_run" in str(steps["Keep the dry-run site"]["if"])


def test_weekly_fails_the_run_after_a_site_failure(tmp_path: Path) -> None:
    steps = weekly_steps(tmp_path)
    assert list(steps)[-1] == "Report a site failure"
    assert steps["Site build"]["id"] == "site_build"
    assert steps["Site deploy"]["id"] == "site_deploy"
    report = steps["Report a site failure"]
    assert "steps.site_build.outcome == 'failure'" in str(report["if"])
    assert "steps.site_deploy.outcome == 'failure'" in str(report["if"])
    assert "exit 1" in str(report["run"])
