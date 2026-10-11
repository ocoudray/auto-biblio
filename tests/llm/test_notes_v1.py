import pytest
from builders import make_item

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.kb.notes import DeepAnalysis
from auto_biblio.extract import ExtractedText
from auto_biblio.llm.prompts.notes_v1 import deep_analysis_task, short_note_task
from auto_biblio.repo_config.profile import Theme

THEMES = (Theme(id="agentic", label="Agents", description="Agent  harnesses."),)
EXTRACTED = ExtractedText(
    text="Full text, code at https://github.com/o/r and docs https://docs.example.org/x",
    source="full_text",
    links=("https://github.com/o/r",),
)


def analysis(*urls: str) -> DeepAnalysis:
    return DeepAnalysis(
        summary="s",
        contribution="c",
        relevance="r",
        problem="p",
        method=("m",),
        results=(),
        limitations=(),
        positioning="pos",
        takeaways=("t",),
        further_reading=urls,
        verdict="v",
        confidence="medium",
    )


def test_further_reading_must_come_from_text() -> None:
    task = deep_analysis_task(make_item(), EXTRACTED, THEMES)
    ok = analysis("https://github.com/o/r", "https://docs.example.org/x", "https://example.com/x")
    assert task.validate(ok, "m") == ok
    with pytest.raises(LLMOutputInvalidError, match=r"invented\.example"):
        task.validate(analysis("https://invented.example/paper"), "m")


def test_prompts_carry_themes_language_and_text() -> None:
    task = short_note_task(make_item(title="Durable"), EXTRACTED, THEMES)
    assert task.role == "short_note"
    assert task.prompt_version == "short_note_v1"
    assert "Agents: Agent harnesses." in task.system_prompt
    assert "French" in task.system_prompt
    assert '"text_source": "full_text"' in task.user_prompt
    assert task.output_type.__name__ == "ShortNote"


def test_prompts_deterministic() -> None:
    first = deep_analysis_task(make_item(), EXTRACTED, THEMES)
    second = deep_analysis_task(make_item(), EXTRACTED, THEMES)
    assert (first.system_prompt, first.user_prompt) == (second.system_prompt, second.user_prompt)
    assert first.prompt_version == "deep_analysis_v1"
