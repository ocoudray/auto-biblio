from auto_biblio.extract import clean_text, collect_links


def test_clean_cuts_references() -> None:
    text = "Intro text.\n\n## 5 References\n\n[1] cited"
    assert clean_text(text, 1000) == "Intro text."
    assert clean_text("Body\nAcknowledgments\nThanks", 1000) == "Body"
    assert clean_text("Body\n\nAppendix A. Proofs", 1000) == "Body"
    assert (
        clean_text("We discuss references to prior work.", 1000)
        == "We discuss references to prior work."
    )


def test_clean_truncates_at_word_boundary() -> None:
    assert clean_text("alpha beta gamma delta", 12) == "alpha beta"
    assert clean_text("x" * 50, 10) == "x" * 10


def test_links_collected() -> None:
    text = "See https://github.com/o/r. And (https://a.org/x), https://a.org/x"
    assert collect_links(text) == ("https://a.org/x", "https://github.com/o/r")
