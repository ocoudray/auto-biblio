import pytest
from builders import make_item

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.triage import TriageBatch, TriageInput, TriageVerdict
from auto_biblio.llm.prompts.triage_v1 import make_batches, system_prompt, to_inputs, triage_task
from auto_biblio.repo_config.profile import Theme

THEMES = (
    Theme(id="agentic", label="Agents", description="Agent   harnesses\n and MCP."),
    Theme(id="rag", label="RAG", description="Retrieval."),
)


def inputs(n: int) -> tuple[TriageInput, ...]:
    return to_inputs(
        [
            (make_item(item_id=f"arxiv:2410.{i:05}", title=f"T{i}"), "text", "abstract")
            for i in range(n)
        ]
    )


def test_system_prompt_lists_every_theme() -> None:
    prompt = system_prompt(THEMES)
    assert "id: agentic" in prompt
    assert "description: Agent harnesses and MCP." in prompt
    assert "id: rag" in prompt


def test_refs_are_sequential() -> None:
    assert [i.ref for i in inputs(3)] == ["i01", "i02", "i03"]
    assert inputs(1)[0].source == "arxiv"


def test_batches_respect_size() -> None:
    assert [len(b) for b in make_batches(inputs(5), 2)] == [2, 2, 1]
    assert make_batches((), 3) == []


def test_task_validation() -> None:
    task = triage_task(inputs(2), THEMES)
    verdict = TriageVerdict(
        ref="i01",
        relevance={ThemeId("agentic"): 4},
        item_type="tool",
        novelty="high",
        confidence="high",
        reason="ok",
    )
    with pytest.raises(LLMOutputInvalidError, match="missing"):
        task.validate(TriageBatch(verdicts=(verdict,)), "m")
    both = TriageBatch(verdicts=(verdict, verdict.model_copy(update={"ref": "i02"})))
    assert task.validate(both, "m") == both


def test_prompt_is_deterministic() -> None:
    first, second = triage_task(inputs(2), THEMES), triage_task(inputs(2), THEMES)
    assert first.user_prompt == second.user_prompt
    assert first.system_prompt == second.system_prompt
    assert first.prompt_version == "triage_v1"
