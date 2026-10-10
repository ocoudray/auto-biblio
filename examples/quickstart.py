"""Minimal library usage: build a validated model and call the core logic.

Run with `uv run python examples/quickstart.py`.
"""

from auto_biblio.core import Greeting, greet


def main() -> None:
    """Print a greeting computed by the package."""
    print(greet(Greeting(name="Ada")))


if __name__ == "__main__":
    main()
