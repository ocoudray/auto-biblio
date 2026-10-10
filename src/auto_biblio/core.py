"""Core domain logic: pure, typed and free of I/O."""

from pydantic import BaseModel, ConfigDict, Field


class Greeting(BaseModel):
    """A validated request to greet someone."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)


def greet(greeting: Greeting) -> str:
    """Build a friendly greeting message.

    Args:
        greeting: Who to greet.

    Returns:
        The greeting message.
    """
    return f"Hello, {greeting.name}!"
