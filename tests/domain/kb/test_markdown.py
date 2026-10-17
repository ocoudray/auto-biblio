import pytest

from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.kb.markdown import split_front_matter


def test_split_front_matter() -> None:
    meta, body = split_front_matter("---\ntitle: T\n---\n\n# T\n\nText.\n", "x.md")
    assert meta == {"title": "T"}
    assert body == "\n# T\n\nText.\n"


def test_split_front_matter_requires_front_matter() -> None:
    with pytest.raises(KBFormatError, match="missing YAML front-matter"):
        split_front_matter("# T\n", "x.md")


def test_split_front_matter_requires_a_mapping() -> None:
    with pytest.raises(KBFormatError, match="not a mapping"):
        split_front_matter("---\n- a\n---\n# T\n", "x.md")
