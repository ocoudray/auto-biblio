from datetime import date

import pytest
from builders import make_note

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.pages import ThemePageContent, ToolRef
from auto_biblio.llm.prompts.theme_page_v1 import theme_page_task
from auto_biblio.repo_config.profile import Theme

THEME = Theme(id="agentic", label="Agents", description="Agent harnesses.")
OLD = ThemePageContent(
    overview="Old.",
    key_concepts=(),
    dominant_approaches=(),
    reference_tools=(ToolRef(name="MCP", url="https://modelcontextprotocol.io"),),
    open_questions=(),
    further_reading=("https://arxiv.org/abs/1",),
)


def page(**changes: object) -> ThemePageContent:
    return OLD.model_copy(update={"overview": "New."} | changes)


def test_theme_task_rejects_lost_link() -> None:
    task = theme_page_task(THEME, OLD, [make_note("arxiv:1")], 10_000)
    assert task.validate(page(), "m").overview == "New."
    with pytest.raises(LLMOutputInvalidError, match="removed_links"):
        task.validate(page(further_reading=()), "m")


def test_theme_task_rejects_unknown_note_id() -> None:
    task = theme_page_task(THEME, None, [make_note("arxiv:1")], 10_000)
    known = page(reference_tools=(ToolRef(name="X", url="https://x", note_id=ItemId("arxiv:1")),))
    assert task.validate(known, "m") == known
    unknown = page(reference_tools=(ToolRef(name="X", url="https://x", note_id=ItemId("gh:o/r")),))
    with pytest.raises(LLMOutputInvalidError, match="gh:o/r"):
        task.validate(unknown, "m")


def test_notes_truncated_to_budget_most_recent_first() -> None:
    notes = [
        make_note(
            f"arxiv:{i}", depth="deep" if i == 2 else "short", analyzed_at=date(2026, 10, i + 1)
        )
        for i in range(5)
    ]
    task = theme_page_task(THEME, None, notes, 600)
    assert '"id": "arxiv:4"' in task.user_prompt
    assert '"id": "arxiv:0"' not in task.user_prompt
    assert '"previous_page": null' in task.user_prompt
    everything = theme_page_task(THEME, OLD, notes, 100_000)
    assert '"verdict": "Worth it."' in everything.user_prompt
    assert "removed_links" not in everything.user_prompt
    assert everything.role == "synthesis"
