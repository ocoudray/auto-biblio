from datetime import date
from pathlib import PurePosixPath

import pytest

from auto_biblio.domain.errors import KBFormatError, LLMOutputInvalidError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.pages import (
    RemovedLink,
    ThemePage,
    ThemePageContent,
    ThemePageMeta,
    ToolRef,
    check_links_kept,
    page_links,
    parse_theme_page,
    render_theme_page,
)

CONTENT = ThemePageContent(
    overview="Agents  are\nharnessed.",
    key_concepts=("Tool use", "Memory"),
    dominant_approaches=("ReAct loops",),
    reference_tools=(
        ToolRef(
            name="pydantic-ai [lib]",
            url="https://github.com/pydantic/pydantic-ai",
            note_id=ItemId("gh:pydantic/pydantic-ai"),
        ),
        ToolRef(name="MCP", url="https://modelcontextprotocol.io"),
    ),
    open_questions=("How to evaluate agents?",),
    further_reading=("https://arxiv.org/abs/2410.12345",),
)
META = ThemePageMeta(
    theme="agentic",  # pyright: ignore[reportArgumentType] - ThemeId at runtime
    label="Architectures agentiques",
    updated_at=date(2026, 10, 11),
    prompt_version="theme_page_v1",
    model_id="google:gemini-3.5-flash",
    notes=(ItemId("gh:pydantic/pydantic-ai"), ItemId("arxiv:2410.12345")),
)
PATHS = {ItemId("gh:pydantic/pydantic-ai"): PurePosixPath("notes/tools/gh-pydantic-pydantic-ai.md")}


def test_theme_page_roundtrip() -> None:
    page = ThemePage(meta=META, content=CONTENT)
    text = render_theme_page(page, PATHS)
    assert (
        "[pydantic-ai (lib)](https://github.com/pydantic/pydantic-ai)"
        " · [fiche](../notes/tools/gh-pydantic-pydantic-ai.md)" in text
    )
    assert parse_theme_page(text, "themes/agentic.md") == page
    assert render_theme_page(parse_theme_page(text, "x"), PATHS) == text
    assert page.path == PurePosixPath("themes/agentic.md")


def test_tool_note_without_known_path() -> None:
    text = render_theme_page(ThemePage(meta=META, content=CONTENT))
    assert "<!-- note:gh:pydantic/pydantic-ai -->" in text
    assert (
        parse_theme_page(text, "x").content.reference_tools[0].note_id == "gh:pydantic/pydantic-ai"
    )


def test_unreadable_tool_line() -> None:
    text = render_theme_page(ThemePage(meta=META, content=CONTENT)).replace(
        "[MCP](https://modelcontextprotocol.io)", "MCP"
    )
    with pytest.raises(KBFormatError, match="reference tool"):
        parse_theme_page(text, "x")


def test_invalid_meta() -> None:
    with pytest.raises(KBFormatError, match="invalid theme page"):
        parse_theme_page("---\ntheme: agentic\n---\n# t\n", "x")


def rewrite(**changes: object) -> ThemePageContent:
    return CONTENT.model_copy(update=changes)


def test_link_dropped_without_reason_rejected() -> None:
    new = rewrite(further_reading=())
    with pytest.raises(LLMOutputInvalidError, match=r"missing: https://arxiv\.org/abs/2410\.12345"):
        check_links_kept(CONTENT, new, "m")
    blank = rewrite(
        further_reading=(),
        removed_links=(RemovedLink(url="https://arxiv.org/abs/2410.12345", reason="  "),),
    )
    with pytest.raises(LLMOutputInvalidError):
        check_links_kept(CONTENT, blank, "m")


def test_link_removed_with_reason_accepted() -> None:
    new = rewrite(
        further_reading=(),
        removed_links=(
            RemovedLink(url="https://arxiv.org/abs/2410.12345", reason="Superseded by v2."),
        ),
    )
    assert check_links_kept(CONTENT, new, "m") == new


def test_first_page_has_no_constraint() -> None:
    assert check_links_kept(None, CONTENT, "m") == CONTENT
    assert page_links(CONTENT) == {
        "https://github.com/pydantic/pydantic-ai",
        "https://modelcontextprotocol.io",
        "https://arxiv.org/abs/2410.12345",
    }
