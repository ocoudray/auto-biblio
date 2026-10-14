from pathlib import Path

from auto_biblio.publish.render import render_digest, render_digest_markdown
from auto_biblio.publish.view import (
    DigestItem,
    DigestView,
    HealthSummary,
    KBChange,
    KBChanges,
    SourceHealth,
    ThemeSection,
)

SNAPSHOT = Path(__file__).parent.parent / "fixtures" / "digest" / "expected.html"


def item(title: str, **extra: object) -> DigestItem:
    base: dict[str, object] = {
        "title": title,
        "url": "https://arxiv.org/abs/2410.12345",
        "sources": "arxiv, hn",
        "reason": "Introduces a durable harness.",
        "item_type": "advance",
        "revenant": False,
        "unverified": False,
        "up_url": "https://github.com/me/data/issues/new?title=up",
        "down_url": "https://github.com/me/data/issues/new?title=down",
    }
    return DigestItem.model_validate(base | extra)


def view() -> DigestView:
    return DigestView(
        week="2026-W41",
        sections=(
            ThemeSection(
                label="Agents", items=(item("Agent <script>x</script>"), item("Old", revenant=True))
            ),
        ),
        discoveries=(item("Popular thing", unverified=True, reason=None, item_type=None),),
        health=HealthSummary(
            failing_sources=(SourceHealth(source="import-ai", consecutive_failures=3),)
        ),
        scoring_version="fixed-v1",
        auc=None,
        unverified=1,
        cost_usd=0.0123,
        tokens=4200,
        degradations=("fallback triage: m (ProviderQuotaError)",),
    )


def test_html_escapes_titles() -> None:
    html, text = render_digest(view())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Agent <script>x</script>" in text  # plain text is not HTML


def test_render_contents() -> None:
    html, text = render_digest(view())
    for fragment in (
        "Veille IA — 2026-W41",
        "revient au goût du jour",
        "non vérifié",
        "Découvertes",
        "import-ai en échec depuis 3",
        "4200 tokens",
        "0.012 $",
    ):
        assert fragment in html
    assert "## Agents" in text
    assert "! fallback triage" in text


def test_render_snapshot() -> None:
    html, _ = render_digest(view())
    assert html == SNAPSHOT.read_text(encoding="utf-8")


def test_render_kb_changes_and_note_links() -> None:
    changed = view().model_copy(
        update={
            "kb_changes": KBChanges(
                notes=(
                    KBChange(
                        title="Durable Agents", change="fiche approfondie", url="https://kb/x.md"
                    ),
                ),
                theme="Agents",
                theme_url="https://kb/themes/agentic.md",
                links_removed=("https://old : Dead.",),
            ),
            "sections": (
                ThemeSection(
                    label="Agents",
                    items=(item("With note", note_url="https://kb/x.md", verdict="À lire."),),
                ),
            ),
        }
    )
    html, text = render_digest(changed)
    assert "Évolutions de la base" in html
    assert '<a href="https://kb/x.md">Durable Agents</a> : fiche approfondie' in html
    assert 'Page thème <a href="https://kb/themes/agentic.md">Agents</a> réécrite' in html
    assert "Analyse : À lire." in html
    assert ">fiche</a>" in html
    assert "## Évolutions de la base" in text
    assert "Fiche : https://kb/x.md" in text
    assert "- Lien retiré : https://old : Dead." in text


def test_online_link_when_the_site_is_set() -> None:
    html, text = render_digest(view().model_copy(update={"online_url": "https://v/digests/w/"}))
    assert "Voir en ligne" in html
    assert 'href="https://v/digests/w/"' in html
    assert "Voir en ligne : https://v/digests/w/" in text


def test_no_online_link_without_site() -> None:
    html, text = render_digest(view())
    assert "Voir en ligne" not in html
    assert "Voir en ligne" not in text


def markdown_view() -> DigestView:
    return view().model_copy(
        update={
            "sections": (
                ThemeSection(
                    label="Agents",
                    items=(
                        item(
                            "Durable | Agents", note_url="../notes/papers/x.md", verdict="À lire."
                        ),
                    ),
                ),
            ),
            "kb_changes": KBChanges(
                notes=(
                    KBChange(title="Durable", change="nouvelle fiche", url="../notes/papers/x.md"),
                ),
            ),
        }
    )


def test_markdown_digest_lists_items_and_notes() -> None:
    page = render_digest_markdown(markdown_view())
    assert page.startswith("# Digest — 2026-W41\n")
    assert "## Agents" in page
    assert "[Durable | Agents](https://arxiv.org/abs/2410.12345)" in page
    assert "[fiche](../notes/papers/x.md)" in page
    assert "Analyse : À lire." in page
    assert "## Découvertes" in page
    assert "## Évolutions de la base" in page
    assert "- [Durable](../notes/papers/x.md) : nouvelle fiche" in page


def test_markdown_digest_has_no_feedback_nor_health() -> None:
    page = render_digest_markdown(markdown_view())
    assert "issues/new" not in page
    assert "import-ai" not in page
    assert "tokens" not in page
