import runpy
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def run_example(name: str, capsys: pytest.CaptureFixture[str]) -> str:
    runpy.run_path(str(EXAMPLES / name), run_name="__main__")
    return capsys.readouterr().out


def test_dedup_example(capsys: pytest.CaptureFixture[str]) -> None:
    output = run_example("dedup.py", capsys).strip()
    assert output == "arxiv:2410.12345 — 3 sightings (arxiv, hf-papers, hn)"
