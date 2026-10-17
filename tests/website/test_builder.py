import tomllib
from pathlib import Path, PurePosixPath

import pytest
from builders import make_note, make_theme_page

from auto_biblio.domain.errors import SiteBuildError, SiteOutputError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import render_note
from auto_biblio.domain.kb.pages import render_theme_page
from auto_biblio.domain.website.plan import NavEntry, SiteInputs, SitePlan, plan_site
from auto_biblio.repo_config.profile import Profile
from auto_biblio.website.builder import SiteBuilder, render_config

PROFILE = Profile.model_validate(
    {"themes": [{"id": "agentic", "label": "Agents", "description": "a"}]}
)


def small_plan() -> SitePlan:
    note = make_note("a:1")
    theme = make_theme_page(notes=("a:1",))
    kb_files = {
        note.path: render_note(note),
        PurePosixPath("themes/agentic.md"): render_theme_page(theme, {ItemId("a:1"): note.path}),
        PurePosixPath("changelog/2026-W42.md"): "# Évolutions — 2026-W42\n",
    }
    digest = "# Digest — 2026-W42\n\n- [Title](https://x) · [fiche](../notes/papers/a-1.md)\n"
    return plan_site(
        SiteInputs(
            title="Veille IA", profile=PROFILE, kb_files=kb_files, digests={"2026-W42": digest}
        )
    )


def test_config_round_trips() -> None:
    nav = (
        NavEntry(title="Accueil", path="index.md"),
        NavEntry(title="Fiches", children=(NavEntry(title="Articles", path="notes/papers.md"),)),
    )
    config = tomllib.loads(render_config('Veille "IA"', nav))["project"]
    assert config["site_name"] == 'Veille "IA"'
    assert config["nav"] == [{"Accueil": "index.md"}, {"Fiches": [{"Articles": "notes/papers.md"}]}]
    assert config["theme"]["language"] == "fr"


def test_build_produces_linked_pages(tmp_path: Path) -> None:
    out = tmp_path / "out"
    SiteBuilder(strict=True).build(small_plan(), "Veille IA", out)
    digest = (out / "digests/2026-W42/index.html").read_text(encoding="utf-8")
    assert 'href="../../notes/papers/a-1/"' in digest
    index = (out / "notes/papers/index.html").read_text(encoding="utf-8")
    assert 'href="../papers/a-1/"' in index
    assert (out / "notes/papers/a-1/index.html").exists()
    assert (out / "themes/agentic/index.html").exists()
    assert (out / "search.json").exists()


def test_empty_plan_builds(tmp_path: Path) -> None:
    plan = plan_site(SiteInputs(title="Veille IA", profile=PROFILE, kb_files={}, digests={}))
    SiteBuilder(strict=True).build(plan, "Veille IA", tmp_path / "out")
    assert (tmp_path / "out/index.html").exists()


def test_rebuild_removes_stale_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    SiteBuilder(strict=True).build(small_plan(), "Veille IA", out)
    (out / "old.html").write_text("x")
    SiteBuilder(strict=True).build(small_plan(), "Veille IA", out)
    assert not (out / "old.html").exists()


def test_build_into_an_empty_directory(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    SiteBuilder(strict=True).build(small_plan(), "Veille IA", out)
    assert (out / "index.html").exists()


def test_refuses_to_replace_a_directory_it_did_not_build(tmp_path: Path) -> None:
    out = tmp_path / "data"
    out.mkdir()
    (out / "precious.md").write_text("mine")
    with pytest.raises(SiteOutputError, match="not a site built by auto-biblio"):
        SiteBuilder().build(small_plan(), "Veille IA", out)
    assert (out / "precious.md").read_text() == "mine"


def test_refuses_a_file_as_output(tmp_path: Path) -> None:
    out = tmp_path / "file"
    out.write_text("x")
    with pytest.raises(SiteOutputError, match="not a directory"):
        SiteBuilder().build(small_plan(), "Veille IA", out)


def test_broken_link_fails_in_strict_mode(tmp_path: Path) -> None:
    plan = small_plan()
    broken = plan.model_copy(
        update={"pages": {**plan.pages, PurePosixPath("index.md"): "[x](nope.md)\n"}}
    )
    with pytest.raises(SiteBuildError, match="zensical build failed"):
        SiteBuilder(strict=True).build(broken, "Veille IA", tmp_path / "out")


def test_config_loads_mathjax() -> None:
    config = tomllib.loads(render_config("Veille IA", ()))["project"]
    assert config["extra_javascript"] == [
        "javascripts/mathjax.js",
        "https://unpkg.com/mathjax@3/es5/tex-mml-chtml.js",
    ]


def test_build_renders_math_mermaid_and_figures(tmp_path: Path) -> None:
    page = (
        "# Attention\n\nLe score $q \\cdot k$ :\n\n$$\nsoftmax(x)\n$$\n\n"
        "```mermaid\ngraph LR\n  A --> B\n```\n\n![Figure](img/a.svg)\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    plan = SitePlan(
        pages={
            PurePosixPath("index.md"): "# Accueil\n",
            PurePosixPath("wiki/llm/attention.md"): page,
        },
        nav=(NavEntry(title="Attention", path="wiki/llm/attention.md"),),
        assets={PurePosixPath("wiki/llm/img/a.svg"): b'<svg xmlns="http://www.w3.org/2000/svg"/>'},
    )
    out = tmp_path / "out"
    SiteBuilder(strict=True).build(plan, "Veille IA", out)
    html = (out / "wiki/llm/attention/index.html").read_text(encoding="utf-8")
    assert 'class="arithmatex"' in html
    assert '<pre class="mermaid">' in html
    assert "<table>" in html
    assert (out / "javascripts/mathjax.js").exists()
    assert (out / "wiki/llm/img/a.svg").read_bytes().startswith(b"<svg")
