import pytest
from builders import make_note

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.wiki.catalog import CatalogEntry
from auto_biblio.domain.wiki.links import LinkResult
from auto_biblio.llm.prompts.wiki_link_v1 import (
    VERSION,
    LinkBatch,
    LinkInput,
    LinkVerdict,
    to_inputs,
    to_results,
    wiki_link_task,
)

ENTRIES = (
    CatalogEntry(id="llm/attention", title="Attention", aliases=("self-attention",)),
    CatalogEntry(id="llm/multi-head-attention", title="Multi-head attention", aliases=("MHA",)),
)


def batch() -> tuple[LinkInput, ...]:
    return to_inputs([make_note("a:1"), make_note("a:2")])


def test_inputs() -> None:
    first = batch()[0]
    assert first.ref == "n01"
    assert first.title == "Title a:1"
    assert first.summary == "About a:1."
    assert first.contribution == "New."


def test_task_carries_the_catalog() -> None:
    task = wiki_link_task(batch(), ENTRIES)
    assert task.role == "wiki_link"
    assert task.prompt_version == VERSION
    assert '"llm/multi-head-attention"' in task.system_prompt
    assert "n02" in task.user_prompt


def test_every_ref_is_required() -> None:
    task = wiki_link_task(batch(), ENTRIES)
    output = LinkBatch(links=(LinkVerdict(ref="n01", notions=(), missing=()),))
    with pytest.raises(LLMOutputInvalidError, match="n02"):
        task.validate(output, "m")


def test_results_map_titles_and_drop_unknown_ids() -> None:
    inputs = batch()
    output = LinkBatch(
        links=(
            LinkVerdict(
                ref="n01",
                notions=("Multi-head attention", "llm/nope", "llm/attention"),
                missing=("a", "b", "c", "d"),
            ),
            LinkVerdict(ref="n02", notions=("MHA",), missing=()),
        )
    )
    results = to_results(inputs, output, ENTRIES)
    assert results["n01"] == LinkResult(
        notions=("llm/attention", "llm/multi-head-attention"), missing=("a", "b", "c")
    )
    assert results["n02"] == LinkResult(notions=("llm/multi-head-attention",), missing=())
