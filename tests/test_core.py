import pytest
from pydantic import ValidationError

from auto_biblio.core import Greeting, greet


def test_greet_returns_message() -> None:
    assert greet(Greeting(name="Ada")) == "Hello, Ada!"


def test_greeting_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Greeting(name="")


def test_greeting_is_immutable() -> None:
    greeting = Greeting(name="Ada")
    with pytest.raises(ValidationError):
        # Assigning a frozen field on purpose: pyright rightly flags it, the test proves
        # it also fails at runtime.
        greeting.name = "Bob"  # pyright: ignore[reportAttributeAccessIssue]
