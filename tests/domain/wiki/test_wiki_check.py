from pathlib import PurePosixPath

from auto_biblio.domain.wiki.check import Problem, check_wiki
from auto_biblio.domain.wiki.pages import load_wiki

P = PurePosixPath
THEMES = frozenset({"agentic", "rag"})
INDEX = "---\ntitle: LLM\norder: [llm/embeddings, llm/attention, llm/transformer]\n---\n\nIntro.\n"


def notion(
    title: str = "T",
    *,
    meta: str = "",
    summary: str = "Résumé.",
    body: str = "",
    refs: bool = True,
) -> str:
    references = "\n## Références fondatrices\n\n- Ref.\n" if refs else ""
    return (
        f"---\ntitle: {title}\nupdated_at: 2026-10-20\n{meta}---\n\n# {title}\n\n"
        f"{summary}\n\n## Intuition\n\n{body}\n{references}"
    )


def problems(files: dict[PurePosixPath, str], assets: tuple[str, ...] = ()) -> list[str]:
    wiki = load_wiki({P("llm/index.md"): INDEX, **files}, [P(a) for a in assets])
    return [str(p) for p in check_wiki(wiki, THEMES)]


def test_valid_wiki() -> None:
    files = {
        P("llm/embeddings.md"): notion(meta="themes: [rag]\n"),
        P("llm/attention.md"): notion(
            meta="prerequisites: [llm/embeddings]\nrelated: [llm/transformer]\n",
            body="![Poids](img/w.svg)\n\n*Figure originale.*\n\nVoir [embeddings](embeddings.md).",
        ),
    }
    assert problems(files, ("llm/img/w.svg",)) == []


def test_problem_str() -> None:
    assert str(Problem(origin="llm/a.md", message="bad")) == "llm/a.md: bad"


def test_unreadable_page() -> None:
    assert problems({P("llm/x.md"): "no front matter"}) == [
        "llm/x.md: unreadable: missing YAML front-matter"
    ]


def test_unknown_prerequisite_and_related() -> None:
    page = notion(meta="prerequisites: [llm/nope]\nrelated: [rag/none]\n")
    assert problems({P("llm/attention.md"): page}) == [
        "llm/attention.md: unknown prerequisite llm/nope",
        "llm/attention.md: unknown related notion rag/none",
    ]


def test_order_entry_of_another_domain() -> None:
    index = INDEX.replace("llm/transformer]", "llm/transformer, rag/x]")
    wiki = load_wiki({P("llm/index.md"): index}, [])
    assert [str(p) for p in check_wiki(wiki, THEMES)] == [
        "llm/index.md: order entry rag/x is not in domain llm"
    ]


def test_prerequisite_cycle_reported_once() -> None:
    files = {
        P("llm/embeddings.md"): notion(meta="prerequisites: [llm/attention]\n"),
        P("llm/attention.md"): notion(meta="prerequisites: [llm/embeddings]\n"),
    }
    assert problems(files) == [
        "llm/attention.md: prerequisite cycle: llm/attention → llm/embeddings → llm/attention"
    ]


def test_unknown_theme() -> None:
    assert problems({P("llm/attention.md"): notion(meta="themes: [cooking]\n")}) == [
        "llm/attention.md: unknown theme cooking"
    ]


def test_missing_summary_and_references() -> None:
    assert problems({P("llm/attention.md"): notion(summary="", refs=False)}) == [
        "llm/attention.md: missing section ## Références fondatrices",
        "llm/attention.md: missing summary under the title",
    ]


def test_missing_image_and_caption() -> None:
    page = notion(body="![A](img/a.svg)\n\nNo caption.\n\n![B](img/b.svg)\n\n*Source : X, CC-BY.*")
    assert problems({P("llm/attention.md"): page}, ("llm/img/b.svg",)) == [
        "llm/attention.md: image img/a.svg has no provenance caption",
        "llm/attention.md: missing image img/a.svg",
    ]


def test_notion_outside_order_and_domain_without_index() -> None:
    files = {P("llm/extra.md"): notion(), P("rag/bm25.md"): notion()}
    assert problems(files) == [
        "llm/extra.md: not listed in llm/index.md order",
        "rag/bm25.md: domain rag has no index.md",
    ]


def test_broken_wiki_link() -> None:
    page = notion(body="See [x](missing.md) and [kb](../../notes/papers/a.md#x).")
    assert problems({P("llm/attention.md"): page}) == ["llm/attention.md: broken link missing.md"]
